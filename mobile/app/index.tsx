import { useCallback, useEffect, useRef, useState } from "react";
import * as ImagePicker from "expo-image-picker";
import { ActivityIndicator, Animated, Image, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import * as SecureStore from "expo-secure-store";

const API_BASE = (process.env.EXPO_PUBLIC_VEGZ_SHOP_API_URL || "http://10.0.2.2:8002").replace(/\/$/, "");

type Shop = { name: string; city: string; shop_type: string; approval_status: string; is_open: boolean; accepts_orders: boolean };
type CatalogItem = { name: string; category: string; description: string; image_url: string; unit: string };
type Product = { id: number; name: string; category: string; image_url: string; image_urls?: string[]; price: number; unit: string; stock_qty: number; is_available: boolean; approval_status?: string };
type Order = { id: number; customer_name: string; customer_phone: string; delivery_address: string; total_amount: number; status: string; note?: string };
type Json = Record<string, unknown>;

async function api<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(API_BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) },
  });
  const data = await response.json().catch(() => ({} as Json));
  if (!response.ok) throw new Error(String((data as Json).detail || `Request failed (${response.status})`));
  return data as T;
}

export default function ShopApp() {
  const enter = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(enter, { toValue: 1, duration: 460, useNativeDriver: true }).start();
    return () => enter.stopAnimation();
  }, [enter]);

  const [token, setToken] = useState("");
  const [shop, setShop] = useState<Shop | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("123456");
  const [city, setCity] = useState("Hubli");
  const [shopType, setShopType] = useState("vegetable");
  const [selected, setSelected] = useState<CatalogItem | null>(null);
  const [price, setPrice] = useState("35");
  const [stock, setStock] = useState("20");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (session: string) => {
    const [profile, catalogItems, productItems] = await Promise.all([
      api<Shop>("/api/shop", session),
      api<CatalogItem[]>("/api/catalog", session),
      api<Product[]>("/api/products", session),
    ]);
    setShop(profile); setCatalog(catalogItems); setProducts(productItems);
    try { setOrders(await api<Order[]>("/api/orders", session)); } catch { setOrders([]); }
  }, []);

  useEffect(() => {
    SecureStore.getItemAsync("vegz-shop-token").then(async saved => {
      if (!saved) return;
      try { await load(saved); setToken(saved); } catch { await SecureStore.deleteItemAsync("vegz-shop-token"); }
    }).catch(() => undefined);
  }, [load]);

  async function signIn() {
    setBusy(true); setError("");
    try {
      const result = await api<{ access_token: string; shop: Shop }>("/api/auth/demo-login", undefined, {
        method: "POST", body: JSON.stringify({ phone, demo_code: code, city, shop_type: shopType }),
      });
      await SecureStore.setItemAsync("vegz-shop-token", result.access_token);
      setToken(result.access_token); await load(result.access_token);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in."); }
    finally { setBusy(false); }
  }

  async function refresh() {
    if (!token) return;
    setBusy(true); setError("");
    try { await load(token); } catch (e) { setError(e instanceof Error ? e.message : "Refresh failed."); }
    finally { setBusy(false); }
  }

  async function addProduct() {
    if (!token || !selected) return;
    const amount = Number(price), quantity = Number(stock);
    if (!Number.isFinite(amount) || amount <= 0 || !Number.isInteger(quantity) || quantity < 0) {
      setError("Enter a positive price and a whole-number stock quantity."); return;
    }
    setBusy(true); setError("");
    try {
      await api<Product>("/api/products", token, { method: "POST", body: JSON.stringify({ name: selected.name, category: selected.category, description: selected.description, image_url: selected.image_url, unit: selected.unit, price: amount, stock_qty: quantity, is_available: true }) });
      setSelected(null); await load(token);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not add product."); }
    finally { setBusy(false); }
  }

  async function toggleProduct(product: Product) {
    if (!token) return;
    setBusy(true); setError("");
    try {
      await api(`/api/products/${product.id}`, token, { method: "PATCH", body: JSON.stringify({ is_available: !product.is_available }) });
      await load(token);
    } catch (e) { setError(e instanceof Error ? e.message : "Update failed."); }
    finally { setBusy(false); }
  }
  async function uploadProductImages(product: Product) {
    if (!token || !shop) return;
    if (shop.approval_status !== "approved") {
      setError("Your shop must be approved before uploading product photos.");
      return;
    }
    setBusy(true); setError("");
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsMultipleSelection: true,
        selectionLimit: 2,
        quality: 0.85,
      });
      if (result.canceled || result.assets.length === 0) return;
      if (result.assets.length > 2) throw new Error("Choose one or two additional photos.");
      const form = new FormData();
      result.assets.forEach((asset, index) => {
        const extension = asset.mimeType === "image/png" ? "png" : asset.mimeType === "image/webp" ? "webp" : "jpg";
        form.append("files", {
          uri: asset.uri,
          name: asset.fileName || `vegz-product-${product.id}-${index + 1}.${extension}`,
          type: asset.mimeType || "image/jpeg",
        } as unknown as Blob);
      });
      const response = await fetch(`${API_BASE}/api/products/${product.id}/images`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await response.json().catch(() => ({} as Json));
      if (!response.ok) throw new Error(String((data as Json).detail || "Photo upload failed."));
      await load(token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Photo upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function setAvailability(open: boolean) {
    if (!token || !shop) return;
    setBusy(true); setError("");
    try {
      const updated = await api<Shop>("/api/shop", token, { method: "PATCH", body: JSON.stringify({ is_open: open, accepts_orders: open }) });
      setShop(updated);
    } catch (e) { setError(e instanceof Error ? e.message : "Shop availability update failed."); }
    finally { setBusy(false); }
  }

  async function advanceOrder(order: Order, status: string) {
    if (!token) return;
    setBusy(true); setError("");
    try {
      await api(`/api/orders/${order.id}/status`, token, { method: "PATCH", body: JSON.stringify({ status, reason: status === "rejected" ? "Shop is unable to fulfil this order." : "" }) });
      await load(token);
    } catch (e) { setError(e instanceof Error ? e.message : "Order update failed."); }
    finally { setBusy(false); }
  }

  async function signOut() {
    await SecureStore.deleteItemAsync("vegz-shop-token");
    setToken(""); setShop(null); setProducts([]); setOrders([]); setCatalog([]);
  }

  if (!token || !shop) {
    return <SafeAreaView style={s.safe}><Animated.ScrollView style={{ opacity: enter }} contentContainerStyle={s.page}>
      <Text style={s.brand}>vegz<Text style={s.period}>shop.</Text></Text>
      <Text style={s.eyebrow}>SHOP PARTNER APP</Text><Text style={s.title}>Your shop.<Text style={s.green}> Your business.</Text></Text>
      <Text style={s.sub}>Manage local vegetables and groceries, update stock, and fulfil customer orders.</Text>
      <View style={s.card}><Text style={s.label}>Owner mobile number</Text><TextInput style={s.input} value={phone} onChangeText={setPhone} placeholder="+91 98765 43210" keyboardType="phone-pad" />
        <Text style={s.label}>Shop type</Text><View style={s.choiceRow}>{["vegetable","grocery"].map(type=><Pressable key={type} style={[s.choice,shopType===type&&s.choiceActive]} onPress={()=>setShopType(type)}><Text style={[s.choiceText,shopType===type&&s.choiceTextActive]}>{type==="vegetable"?"Vegetable shop":"Grocery shop"}</Text></Pressable>)}</View>
        <Text style={s.label}>City</Text><View style={s.choiceRow}>{["Hubli","Dharwad"].map(value=><Pressable key={value} style={[s.choice,city===value&&s.choiceActive]} onPress={()=>setCity(value)}><Text style={[s.choiceText,city===value&&s.choiceTextActive]}>{value}</Text></Pressable>)}</View>
        <Text style={s.label}>Development access code</Text><TextInput style={s.input} value={code} onChangeText={setCode} keyboardType="number-pad" />
        <Action label={busy?"Signing in…":"Open my shop"} onPress={signIn} disabled={busy || !phone.trim()} />
      </View>
      <Text style={s.helper}>Development sign-in only. Production launch requires verified OTP authentication and admin approval.</Text>
      {busy&&<ActivityIndicator color="#176b48" />}{!!error&&<Text style={s.error}>{error}</Text>}
    </Animated.ScrollView></SafeAreaView>;
  }

  return <SafeAreaView style={s.safe}><Animated.ScrollView style={{ opacity: enter }} contentContainerStyle={s.page}>
    <View style={s.header}><View><Text style={s.brand}>vegz<Text style={s.period}>shop.</Text></Text><Text style={s.muted}>{shop.name} · {shop.city}</Text></View><Pressable onPress={signOut}><Text style={s.link}>Sign out</Text></Pressable></View>
    <View style={s.hero}><Text style={s.eyebrow}>SHOP WORKSPACE</Text><Text style={s.title}>Your daily market.</Text><Text style={s.sub}>Manage stock and keep customers updated.</Text><View style={s.badge}><View style={[s.dot,shop.approval_status==="approved"?s.dotGood:s.dotWait]}/><Text style={s.badgeText}>{shop.approval_status==="approved"?"Approved shop":"Approval: "+shop.approval_status}</Text></View></View>
    {!!error&&<Text style={s.error}>{error}</Text>}
    <View style={s.metrics}><Metric label="Products" value={String(products.length)}/><Metric label="New orders" value={String(orders.filter(o=>o.status==="placed").length)}/><Metric label="Open" value={shop.is_open?"Yes":"No"}/></View>
    <View style={s.sectionHead}><Text style={s.heading}>Shop availability</Text><Action label={shop.is_open?"Pause orders":"Open shop"} onPress={()=>setAvailability(!shop.is_open)} disabled={busy || shop.approval_status!=="approved"} compact /></View>
    {shop.approval_status!=="approved"&&<Text style={s.helper}>Your registration is waiting for admin approval. You can prepare your catalog now; customers cannot order until approval.</Text>}
    <View style={s.sectionHead}><Text style={s.heading}>Add from Vegz catalog</Text><Text style={s.muted}>{catalog.length} items</Text></View>
    {selected&&<View style={s.card}><Text style={s.cardTitle}>List {selected.name}</Text><Text style={s.muted}>{selected.category} · {selected.unit}</Text>{!!selected.image_url&&<Image source={{uri:selected.image_url}} style={s.preview}/>}
      <Text style={s.label}>Price (₹ / {selected.unit})</Text><TextInput style={s.input} value={price} onChangeText={setPrice} keyboardType="decimal-pad"/>
      <Text style={s.label}>Opening stock</Text><TextInput style={s.input} value={stock} onChangeText={setStock} keyboardType="number-pad"/>
      <View style={s.choiceRow}><Action label="Save listing" onPress={addProduct} disabled={busy} /><Action label="Cancel" onPress={()=>setSelected(null)} secondary /></View></View>}
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.catalogRow}>{catalog.map(item=><Pressable key={item.name} style={s.catalogCard} onPress={()=>{setSelected(item);setPrice("35");setStock("20");}}>{item.image_url?<Image source={{uri:item.image_url}} style={s.catalogImage}/>:<View style={[s.catalogImage,s.imageFallback]}><Text>🥦</Text></View>}<Text style={s.catalogName}>{item.name}</Text><Text style={s.muted}>{item.unit}</Text><Text style={s.addLink}>+ List product</Text></Pressable>)}</Animated.ScrollView>
    <View style={s.sectionHead}><Text style={s.heading}>My products</Text><Pressable onPress={refresh}><Text style={s.link}>↻ Refresh</Text></Pressable></View>
    {products.map(product=><View key={product.id} style={s.rowCard}>{product.image_url?<Image source={{uri:product.image_url}} style={s.thumb}/>:<View style={[s.thumb,s.imageFallback]}><Text>🥬</Text></View>}<View style={s.rowBody}><Text style={s.productName}>{product.name}</Text><Text style={s.muted}>₹{Number(product.price).toFixed(2)} / {product.unit} · Stock {product.stock_qty}</Text><Text style={s.muted}>{product.approval_status!=="approved"?"Awaiting admin approval":product.is_available?"Available to customers":"Unavailable"}</Text>{product.image_urls&&product.image_urls.length>1&&<View style={s.imageGallery}>{product.image_urls.slice(1,3).map((url,index)=><Image key={url+index} source={{uri:url}} style={s.extraPhoto}/>)}</View>}</View><View style={{gap:6}}><Pressable style={s.smallButton} onPress={()=>toggleProduct(product)} disabled={busy}><Text style={s.smallButtonText}>{product.is_available?"Pause":"Enable"}</Text></Pressable><Pressable style={[s.smallButton,shop.approval_status!=="approved"&&s.disabled]} onPress={()=>void uploadProductImages(product)} disabled={busy||shop.approval_status!=="approved"}><Text style={s.smallButtonText}>Add photos</Text></Pressable></View></View>)}
    <View style={s.sectionHead}><Text style={s.heading}>Incoming orders</Text><Text style={s.muted}>{orders.length} total</Text></View>
    {orders.length===0&&<Text style={s.helper}>No approved-shop orders yet.</Text>}
    {orders.map(order=><View key={order.id} style={s.orderCard}><View style={s.orderHead}><Text style={s.cardTitle}>Order #{order.id}</Text><Text style={s.status}>{order.status.replace(/_/g," ")}</Text></View><Text style={s.productName}>{order.customer_name}</Text><Text style={s.muted}>{order.delivery_address}</Text><Text style={s.amount}>₹{Number(order.total_amount).toFixed(2)}</Text>
      <View style={s.choiceRow}>{order.status==="placed"&&<><Action label="Accept" onPress={()=>advanceOrder(order,"accepted")} compact disabled={busy}/><Action label="Reject" onPress={()=>advanceOrder(order,"rejected")} compact secondary disabled={busy}/></>}{order.status==="accepted"&&<Action label="Start preparing" onPress={()=>advanceOrder(order,"preparing")} compact disabled={busy}/>}{order.status==="preparing"&&<Action label="Ready for pickup" onPress={()=>advanceOrder(order,"ready")} compact disabled={busy}/>}{order.status==="ready"&&<Action label="Handed to delivery" onPress={()=>advanceOrder(order,"out_for_delivery")} compact disabled={busy}/>}</View>
    </View>)}
    <Action label={busy?"Working…":"Refresh workspace"} onPress={refresh} disabled={busy}/>
    <Text style={s.helper}>Each listing uses its built-in catalog image and can store up to two extra JPG, PNG or WEBP photos (5 MB maximum per photo).</Text>
  </Animated.ScrollView></SafeAreaView>;
}

function Action({label,onPress,disabled=false,secondary=false,compact=false}:{label:string;onPress:()=>void;disabled?:boolean;secondary?:boolean;compact?:boolean}) {
  return <Pressable onPress={onPress} disabled={disabled} style={[s.action,secondary&&s.actionSecondary,compact&&s.actionCompact,disabled&&s.disabled]}><Text style={[s.actionText,secondary&&s.actionTextSecondary]}>{label}</Text></Pressable>;
}
function Metric({label,value}:{label:string;value:string}) { return <View style={s.metric}><Text style={s.metricValue}>{value}</Text><Text style={s.muted}>{label}</Text></View>; }

const s=StyleSheet.create({
 safe:{flex:1,backgroundColor:"#f6f8f1"},page:{padding:18,paddingTop:20,paddingBottom:42,gap:14},header:{flexDirection:"row",justifyContent:"space-between",alignItems:"center"},brand:{fontSize:28,fontWeight:"900",color:"#176b48",letterSpacing:-1},period:{color:"#ef8a36"},eyebrow:{color:"#176b48",fontSize:10,fontWeight:"900",letterSpacing:2,marginBottom:8},title:{fontSize:31,lineHeight:36,fontWeight:"900",color:"#1b3027"},green:{color:"#176b48"},sub:{fontSize:14,lineHeight:21,color:"#718077",marginTop:7},muted:{fontSize:12,color:"#718077",marginTop:4},card:{backgroundColor:"#fff",padding:16,borderRadius:18,borderWidth:1,borderColor:"#e2e9df",gap:8},label:{fontSize:12,fontWeight:"800",color:"#34483d",marginTop:6},input:{backgroundColor:"#f9fbf7",borderWidth:1,borderColor:"#dbe5d8",borderRadius:10,paddingHorizontal:12,paddingVertical:11,fontSize:15,color:"#1b3027"},choiceRow:{flexDirection:"row",gap:8,flexWrap:"wrap",alignItems:"center"},choice:{borderRadius:10,borderWidth:1,borderColor:"#dbe5d8",paddingVertical:10,paddingHorizontal:12,backgroundColor:"#fff"},choiceActive:{backgroundColor:"#e6f1e3",borderColor:"#176b48"},choiceText:{fontSize:12,color:"#53655a",fontWeight:"700"},choiceTextActive:{color:"#176b48"},action:{backgroundColor:"#176b48",borderRadius:11,paddingVertical:13,paddingHorizontal:15,alignItems:"center",justifyContent:"center",marginTop:7},actionSecondary:{backgroundColor:"#f2f5ee",borderWidth:1,borderColor:"#dbe5d8"},actionCompact:{paddingVertical:9,paddingHorizontal:12,marginTop:0},actionText:{fontSize:12,fontWeight:"900",color:"#fff"},actionTextSecondary:{color:"#176b48"},disabled:{opacity:.55},helper:{fontSize:12,lineHeight:18,color:"#718077"},error:{backgroundColor:"#fff0ed",borderRadius:10,color:"#a33525",padding:12,lineHeight:18},link:{color:"#176b48",fontSize:12,fontWeight:"900"},hero:{padding:18,backgroundColor:"#e6efdc",borderRadius:20},badge:{flexDirection:"row",gap:7,alignItems:"center",alignSelf:"flex-start",backgroundColor:"#fff",paddingVertical:7,paddingHorizontal:10,borderRadius:20,marginTop:12},badgeText:{fontSize:11,color:"#44574a",fontWeight:"700"},dot:{width:8,height:8,borderRadius:4},dotGood:{backgroundColor:"#45a66d"},dotWait:{backgroundColor:"#e59a33"},metrics:{flexDirection:"row",gap:9},metric:{flex:1,backgroundColor:"#fff",borderWidth:1,borderColor:"#e2e9df",borderRadius:14,padding:13},metricValue:{fontSize:23,fontWeight:"900",color:"#176b48"},sectionHead:{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginTop:10,gap:10},heading:{fontSize:19,fontWeight:"900",color:"#1b3027"},catalogRow:{gap:10,paddingVertical:2},catalogCard:{width:145,backgroundColor:"#fff",borderRadius:14,borderWidth:1,borderColor:"#e2e9df",padding:10},catalogImage:{width:"100%",height:86,borderRadius:10,resizeMode:"cover"},catalogName:{fontSize:13,fontWeight:"900",color:"#1b3027",marginTop:7},addLink:{color:"#176b48",fontSize:11,fontWeight:"900",marginTop:8},imageFallback:{alignItems:"center",justifyContent:"center",backgroundColor:"#edf3e6"},preview:{height:130,width:"100%",borderRadius:12,resizeMode:"cover"},rowCard:{flexDirection:"row",alignItems:"center",gap:10,backgroundColor:"#fff",borderWidth:1,borderColor:"#e2e9df",borderRadius:14,padding:10},thumb:{width:54,height:54,borderRadius:10,resizeMode:"cover"},rowBody:{flex:1},productName:{fontSize:14,fontWeight:"900",color:"#1b3027"},smallButton:{borderRadius:9,backgroundColor:"#edf5e9",paddingHorizontal:10,paddingVertical:8},smallButtonText:{fontSize:11,color:"#176b48",fontWeight:"900"},cardTitle:{fontSize:15,fontWeight:"900",color:"#1b3027"},orderCard:{backgroundColor:"#fff",padding:14,borderRadius:14,borderWidth:1,borderColor:"#e2e9df",gap:8},orderHead:{flexDirection:"row",alignItems:"center",justifyContent:"space-between"},status:{backgroundColor:"#edf5e9",color:"#176b48",paddingVertical:5,paddingHorizontal:8,borderRadius:9,fontSize:10,fontWeight:"900",overflow:"hidden"},imageGallery:{flexDirection:"row",gap:5,marginTop:5},extraPhoto:{width:32,height:32,borderRadius:6,resizeMode:"cover"},amount:{fontWeight:"900",fontSize:18,color:"#176b48",marginTop:3}
});
