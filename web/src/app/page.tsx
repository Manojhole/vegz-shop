"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Shop={id:number;name:string;city:string;shop_type:string;approval_status:string;is_open:boolean;accepts_orders:boolean;address?:string};
type CatalogItem={name:string;category:string;description:string;image_url:string;unit:string};
type Product={id:number;name:string;category:string;description?:string;image_url?:string;image_urls?:string[];price:number|string;unit:string;stock_qty:number;is_available:boolean};
type Order={id:number;customer_name:string;customer_phone:string;delivery_address:string;total_amount:number;status:string;note?:string;created_at?:string};
const API=(process.env.NEXT_PUBLIC_VEGZ_SHOP_API_URL||"http://localhost:8002").replace(/\/$/,"");
const transitions:Record<string,string[]>={placed:["accepted","rejected"],accepted:["preparing"],preparing:["ready"],ready:["out_for_delivery"],out_for_delivery:["delivered"]};
async function request<T>(path:string,token:string,init:RequestInit={}):Promise<T>{
 const response=await fetch(API+path,{...init,headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{}),...(init.headers||{})}});
 const data=await response.json().catch(()=>({}));
 if(!response.ok)throw new Error(String((data as {detail?:string}).detail||"Request failed ("+response.status+")"));
 return data as T;
}

export default function ShopHomePage(){
 const [token,setToken]=useState("");
 const [shop,setShop]=useState<Shop|null>(null);
 const [catalog,setCatalog]=useState<CatalogItem[]>([]);
 const [products,setProducts]=useState<Product[]>([]);
 const [orders,setOrders]=useState<Order[]>([]);
 const [phone,setPhone]=useState("");
 const [code,setCode]=useState("123456");
 const [city,setCity]=useState("Hubli");
 const [shopType,setShopType]=useState("vegetable");
 const [selected,setSelected]=useState<CatalogItem|null>(null);
 const [price,setPrice]=useState("35");
 const [stock,setStock]=useState("20");
 const [edits,setEdits]=useState<Record<number,{price:string;stock:string}>>({});
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [view,setView]=useState<"overview"|"products"|"orders"|"settings">("overview");
 const [name,setName]=useState("My Vegz Shop");
 const [address,setAddress]=useState("");

 const load=useCallback(async(session:string)=>{
  const [profile,items,list]=await Promise.all([
   request<Shop>("/api/shop",session),request<CatalogItem[]>("/api/catalog",session),request<Product[]>("/api/products",session)
  ]);
  setShop(profile);setName(profile.name||"My Vegz Shop");setAddress(profile.address||"");
  setCatalog(items);setProducts(list);
  try{setOrders(await request<Order[]>("/api/orders",session));}catch{setOrders([]);}
 },[]);
 useEffect(()=>{
  const saved=window.localStorage.getItem("vegz-shop-token");
  if(saved){setToken(saved);void load(saved).catch(()=>{window.localStorage.removeItem("vegz-shop-token");setToken("");});}
 },[load]);

 async function login(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();setBusy(true);setError("");
  try{
   const result=await request<{access_token:string;shop:Shop}>("/api/auth/demo-login","",{method:"POST",body:JSON.stringify({phone,demo_code:code,city,shop_type:shopType})});
   window.localStorage.setItem("vegz-shop-token",result.access_token);setToken(result.access_token);await load(result.access_token);setNotice("Shop session started.");
  }catch(e){setError(e instanceof Error?e.message:"Could not sign in.");}
  finally{setBusy(false);}
 }
 async function refresh(){
  if(!token)return;setBusy(true);setError("");
  try{await load(token);setNotice("Shop data refreshed.");}
  catch(e){setError(e instanceof Error?e.message:"Refresh failed.");}
  finally{setBusy(false);}
 }
 async function addProduct(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();if(!token||!selected)return;
  const amount=Number(price),qty=Number(stock);
  if(!Number.isFinite(amount)||amount<=0||!Number.isInteger(qty)||qty<0){setError("Enter a valid price and whole-number stock.");return;}
  setBusy(true);setError("");setNotice("");
  try{
   await request<Product>("/api/products",token,{method:"POST",body:JSON.stringify({name:selected.name,category:selected.category,description:selected.description,image_url:selected.image_url,unit:selected.unit,price:amount,stock_qty:qty,is_available:true})});
   setSelected(null);await load(token);setNotice(`${selected.name} added to your product list.`);
  }catch(e){setError(e instanceof Error?e.message:"Could not add product.");}
  finally{setBusy(false);}
 }
 async function updateProduct(product:Product){
  if(!token)return;const value=edits[product.id]||{price:String(product.price),stock:String(product.stock_qty)};
  const amount=Number(value.price),quantity=Number(value.stock);
  if(!Number.isFinite(amount)||amount<=0||!Number.isInteger(quantity)||quantity<0){setError("Price must be positive and stock must be a whole number.");return;}
  setBusy(true);setError("");setNotice("");
  try{await request(`/api/products/${product.id}`,token,{method:"PATCH",body:JSON.stringify({price:amount,stock_qty:quantity})});await load(token);setNotice(`${product.name} updated.`);}
  catch(e){setError(e instanceof Error?e.message:"Product update failed.");}
  finally{setBusy(false);}
 }
 async function toggleProduct(product:Product){
  if(!token)return;setBusy(true);setError("");setNotice("");
  try{await request(`/api/products/${product.id}`,token,{method:"PATCH",body:JSON.stringify({is_available:!product.is_available})});await load(token);setNotice(product.is_available?"Listing hidden from customers.":"Listing made available if shop is approved.");}
  catch(e){setError(e instanceof Error?e.message:"Could not change availability.");}
  finally{setBusy(false);}
 }
 async function uploadImages(product:Product, files:FileList|null){
  if(!token||!files||files.length===0)return;
  const chosen=Array.from(files);
  if(chosen.length>2){setError("Upload one or two additional images at a time.");return;}
  if(chosen.some(file=>!["image/jpeg","image/png","image/webp"].includes(file.type))){setError("Use JPG, PNG or WEBP images.");return;}
  if(chosen.some(file=>file.size>5*1024*1024)){setError("Each image must be 5 MB or smaller.");return;}
  setBusy(true);setError("");setNotice("");
  try{
   const body=new FormData();chosen.forEach(file=>body.append("files",file));
   const response=await fetch(API+"/api/products/"+product.id+"/images",{method:"POST",headers:{Authorization:"Bearer "+token},body});
   const result=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(String((result as {detail?:string}).detail||"Image upload failed."));
   await load(token);setNotice("Additional product photos uploaded.");
  }catch(e){setError(e instanceof Error?e.message:"Image upload failed.");}
  finally{setBusy(false);}
 }
 async function saveSettings(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();if(!token)return;setBusy(true);setError("");setNotice("");
  try{const saved=await request<Shop>("/api/shop",token,{method:"PATCH",body:JSON.stringify({name,address})});setShop(saved);setName(saved.name);setAddress(saved.address||"");setNotice("Shop details saved.");}
  catch(e){setError(e instanceof Error?e.message:"Could not save settings.");}
  finally{setBusy(false);}
 }
 async function availability(){
  if(!token||!shop)return;setBusy(true);setError("");setNotice("");
  try{const next=await request<Shop>("/api/shop",token,{method:"PATCH",body:JSON.stringify({is_open:!shop.is_open,accepts_orders:!shop.is_open})});setShop(next);setNotice(next.is_open?"Your shop is open for orders.":"Your shop is paused.");}
  catch(e){setError(e instanceof Error?e.message:"Availability update failed.");}
  finally{setBusy(false);}
 }
 async function advanceOrder(order:Order,status:string){
  if(!token)return;setBusy(true);setError("");setNotice("");
  try{
   await request(`/api/orders/${order.id}/status`,token,{method:"PATCH",body:JSON.stringify({status,reason:status==="rejected"?"Unable to fulfil this order.":""})});
   await load(token);setNotice(`Order #${order.id} updated to ${status.replaceAll("_"," ")}.`);
  }catch(e){setError(e instanceof Error?e.message:"Could not update order.");}
  finally{setBusy(false);}
 }
 function logout(){window.localStorage.removeItem("vegz-shop-token");setToken("");setShop(null);setProducts([]);setOrders([]);setCatalog([]);setNotice("");}

 const counts=useMemo(()=>({total:products.length,inStock:products.filter(p=>p.stock_qty>0&&p.is_available).length,out:products.filter(p=>p.stock_qty<=0||!p.is_available).length,newOrders:orders.filter(o=>o.status==="placed").length}),[products,orders]);
 if(!token||!shop){
  return <main className="shop-desk"><header className="shop-topbar"><a className="shop-brand" href="#"><span>V</span> vegz<span className="shop-dot">.</span></a><span className="shop-top-label">SHOP OWNER PORTAL</span></header>
   <section className="shop-login-layout"><div className="shop-welcome"><p className="shop-eyebrow">YOUR LOCAL MARKET, ONLINE</p><h1>Your shop.<br/><span>Your business.</span></h1><p>Manage your everyday catalog, stock and customer orders in one workspace.</p><div className="shop-art">{["🥬","🍅","🥕","🥦"].map((e,i)=><span key={i}>{e}</span>)}</div><div className="shop-hints"><span>✓</span> Catalog photos included <span>✓</span> Stock updates <span>✓</span> Order status</div></div>
    <form className="shop-login-card" onSubmit={login}><div className="shop-mark">V</div><h2>Open your shop</h2><p>Development sign-in; production launch requires verified OTP.</p><label>Owner mobile number</label><input type="tel" required minLength={8} value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+91 98765 43210"/><label>Shop type</label><div className="shop-switch-row">{["vegetable","grocery"].map(v=><button type="button" key={v} onClick={()=>setShopType(v)} className={shopType===v?"selected":""}>{v==="vegetable"?"Vegetable shop":"Grocery shop"}</button>)}</div><label>City</label><div className="shop-switch-row">{["Hubli","Dharwad"].map(v=><button type="button" key={v} onClick={()=>setCity(v)} className={city===v?"selected":""}>{v}</button>)}</div><label>Development access code</label><input value={code} onChange={e=>setCode(e.target.value)} inputMode="numeric" required/><button className="shop-primary" disabled={busy}>{busy?"Signing in…":"Open my shop →"}</button>{error&&<p className="shop-error">{error}</p>}<small>Accounts must be approved by Vegz Admin before products can be sold.</small></form>
   </section><footer className="shop-footer">VEGZ SHOP · LOCAL STORES, ONE MARKET</footer></main>;
 }

 const nav:("overview"|"products"|"orders"|"settings")[]=["overview","products","orders","settings"];
 return <main className="shop-desk"><header className="shop-topbar"><a className="shop-brand" href="#"><span>V</span> vegz<span className="shop-dot">.</span></a><div className="shop-header-right"><span className="shop-pill">{shop.city} · {shop.shop_type}</span><button className="shop-secondary small" onClick={refresh} disabled={busy}>↻ Refresh</button><button className="shop-logout" onClick={logout}>Sign out</button></div></header>
  <div className="shop-layout"><aside className="shop-sidebar"><div className="shop-profile"><span className="shop-avatar">🥬</span><div><strong>{shop.name}</strong><small>{shop.city} shop</small></div></div><nav>{nav.map(n=><button key={n} className={view===n?"active":""} onClick={()=>{setView(n);setError("");setNotice("");}}><span>{({overview:"▦",products:"▤",orders:"▣",settings:"⚙"})[n]}</span>{({overview:"Overview",products:"My products",orders:"Incoming orders",settings:"Shop settings"})[n]}{n==="orders"&&<small>{counts.newOrders}</small>}</button>)}</nav><div className="shop-sidebar-note"><strong>Fresh stock wins</strong><p>Keep your price and availability accurate for your neighbours.</p></div><a className="shop-legacy" href={API} target="_blank" rel="noreferrer">Open original dashboard ↗</a></aside>
   <section className="shop-workspace"><div className="shop-page-heading"><div><p className="shop-eyebrow">VEGZ SHOP / {view.toUpperCase()}</p><h1>{view==="overview"?"Good to see you, shop owner.":view==="products"?"Your product shelf":view==="orders"?"Incoming orders":"Shop settings"}</h1><p>{view==="overview"?"Today’s shop snapshot and key actions.":view==="products"?"List from the catalog and manage prices and stock.":view==="orders"?"Accept orders and keep fulfilment moving.":"Manage the public shop profile and availability."}</p></div><span className={"shop-status "+(shop.approval_status==="approved"?"approved":"pending")}>{shop.approval_status.replaceAll("_"," ")}</span></div>
    {error&&<div className="shop-alert error">{error}</div>}{notice&&<div className="shop-alert success">{notice}</div>}
    {shop.approval_status!=="approved"&&<div className="shop-alert pending"><strong>Registration awaiting admin approval.</strong> You can prepare products, but they remain unavailable for customer orders until approved.</div>}
    {view==="overview"&&<><div className="shop-hero"><div><p className="shop-eyebrow">YOUR DAILY SNAPSHOT</p><h2>Small updates.<br/><span>Happy customers.</span></h2><p>Keep your stock and incoming orders up to date.</p></div><div className="shop-hero-emoji">🧺</div></div><div className="shop-stats"><Metric label="Catalog items" value={counts.total}/><Metric label="In stock" value={counts.inStock}/><Metric label="Hidden / out" value={counts.out}/><Metric label="New orders" value={counts.newOrders}/></div><div className="shop-panel"><div className="shop-panel-heading"><div><h2>Shop availability</h2><p>Only approved shops can accept orders.</p></div><button className={shop.is_open?"shop-secondary":"shop-primary"} onClick={()=>void availability()} disabled={busy||shop.approval_status!=="approved"}>{shop.is_open?"Pause orders":"Open shop"}</button></div><div className="shop-availability-row"><span className={"shop-live-dot "+(shop.is_open&&shop.accepts_orders?"on":"")}/><span>{shop.is_open&&shop.accepts_orders?"Open and accepting orders":"Currently not accepting orders"}</span></div></div><div className="shop-panel"><div className="shop-panel-heading"><div><h2>Latest orders</h2><p>Quickly open the incoming-order queue.</p></div><button className="shop-secondary" onClick={()=>setView("orders")}>View orders →</button></div>{orders.slice(0,3).map(order=><OrderCard key={order.id} order={order} onAdvance={advanceOrder} busy={busy}/>)}</div></>}
    {view==="products"&&<><div className="shop-section-heading"><div><h2>Choose from the Vegz catalog</h2><p>Every product has a built-in image. Shop-specific extra photo uploads remain available in the original dashboard.</p></div><span>{catalog.length} catalog items</span></div>{selected&&<form className="shop-create-card" onSubmit={addProduct}><div className="shop-create-identity">{selected.image_url?<img src={selected.image_url} alt={selected.name}/>:<span>🥦</span>}<div><strong>List {selected.name}</strong><p>{selected.category} · {selected.unit}</p></div></div><div className="shop-fields"><label>Price (₹ / {selected.unit})<input value={price} onChange={e=>setPrice(e.target.value)} inputMode="decimal" required/></label><label>Opening stock<input value={stock} onChange={e=>setStock(e.target.value)} inputMode="numeric" required/></label></div><div className="shop-form-actions"><button className="shop-primary" disabled={busy}>Save listing</button><button type="button" className="shop-secondary" onClick={()=>setSelected(null)}>Cancel</button></div></form>}<div className="shop-catalog-grid">{catalog.map(item=><button type="button" key={item.name} className={"shop-catalog-item "+(selected?.name===item.name?"selected":"")} onClick={()=>{setSelected(item);setPrice("35");setStock("20");}}>{item.image_url?<img src={item.image_url} alt={item.name} loading="lazy"/>:<span className="shop-image-fallback">🥦</span>}<strong>{item.name}</strong><small>{item.category} · {item.unit}</small><span className="shop-catalog-action">+ List product</span></button>)}</div><div className="shop-section-heading"><div><h2>My products</h2><p>Update price, quantity, and customer availability.</p></div><span>{products.length} listings</span></div><div className="shop-product-list">{products.map(product=><ProductCard key={product.id} product={product} value={edits[product.id]||{price:String(product.price),stock:String(product.stock_qty)}} onChange={(v)=>setEdits(old=>({...old,[product.id]:v}))} onSave={()=>void updateProduct(product)} onToggle={()=>void toggleProduct(product)} onUpload={(files)=>void uploadImages(product,files)} busy={busy}/>)}</div>{products.length===0&&<Empty text="Your listed products will appear here after you add them from the catalog."/>}</>}
    {view==="orders"&&<><div className="shop-section-heading"><div><h2>Order queue</h2><p>Move each order through valid fulfilment states.</p></div><span>{orders.length} orders</span></div>{orders.map(order=><OrderCard key={order.id} order={order} onAdvance={advanceOrder} busy={busy}/>)}{orders.length===0&&<Empty text="Orders appear here once your shop is approved, open and accepting orders."/ >}</>}
    {view==="settings"&&<form className="shop-settings" onSubmit={saveSettings}><h2>Shop profile</h2><p>Basic store information. City and shop type are fixed at registration.</p><label>Shop display name<input value={name} onChange={e=>setName(e.target.value)} maxLength={120} required/></label><label>Street address<input value={address} onChange={e=>setAddress(e.target.value)} maxLength={300}/></label><div className="shop-readonly-grid"><div><small>City</small><strong>{shop.city}</strong></div><div><small>Shop type</small><strong>{shop.shop_type}</strong></div><div><small>Approval</small><strong>{shop.approval_status}</strong></div></div><button className="shop-primary" disabled={busy}>Save shop details</button><div className="shop-settings-sep"/><div className="shop-panel-heading"><div><h2>Order availability</h2><p>Pause incoming orders when your shop is closed.</p></div><button type="button" className={shop.is_open?"shop-secondary":"shop-primary"} disabled={busy||shop.approval_status!=="approved"} onClick={()=>void availability()}>{shop.is_open?"Pause orders":"Open shop"}</button></div></form>}
   </section>
  </div>
  <footer className="shop-footer">VEGZ SHOP · Fresh produce. Better neighbourhoods.</footer>
 </main>;
}
function Metric({label,value}:{label:string;value:number}){return <article className="shop-stat"><span>{label}</span><strong>{value}</strong><small>Live shop records</small></article>}
function Empty({text}:{text:string}){return <div className="shop-empty"><span>✓</span><strong>Nothing here yet</strong><p>{text}</p></div>}
function OrderCard({order,onAdvance,busy}:{order:Order;onAdvance:(order:Order,status:string)=>void;busy:boolean}){const choices=transitions[order.status]||[];return <article className="shop-order-card"><div className="shop-order-top"><div><strong>Order #{order.id}</strong><p>{order.customer_name} · {order.customer_phone||"No phone"}</p></div><span className={"shop-status "+(order.status==="delivered"?"approved":"pending")}>{order.status.replaceAll("_"," ")}</span></div><p className="shop-order-address">{order.delivery_address||"Delivery address pending"}</p><div className="shop-order-bottom"><strong>₹{Number(order.total_amount).toFixed(2)}</strong><div>{choices.map(status=><button key={status} className={status==="rejected"?"shop-secondary small":"shop-primary small"} disabled={busy} onClick={()=>void onAdvance(order,status)}>{status.replaceAll("_"," ")}</button>)}</div></div>{order.note&&<small>{order.note}</small>}</article>}
function ProductCard({product,value,onChange,onSave,onToggle,onUpload,busy}:{product:Product;value:{price:string;stock:string};onChange:(v:{price:string;stock:string})=>void;onSave:()=>void;onToggle:()=>void;onUpload:(files:FileList|null)=>void;busy:boolean}){const images=(product.image_urls&&product.image_urls.length?product.image_urls:[product.image_url||""]).filter(Boolean);return <article className="shop-product-row"><div className="shop-product-gallery">{images.map((image,index)=><img key={image+index} src={image} alt={product.name+" photo "+(index+1)}/>)}</div><div className="shop-product-detail"><strong>{product.name}</strong><p>{product.category} · {product.unit}</p><span className={"shop-status "+(product.is_available?"approved":"pending")}>{product.is_available?"Available":"Hidden / out of stock"}</span></div><div className="shop-edit-fields"><label>Price<input value={value.price} onChange={e=>onChange({...value,price:e.target.value})} inputMode="decimal"/></label><label>Stock<input value={value.stock} onChange={e=>onChange({...value,stock:e.target.value})} inputMode="numeric"/></label></div><div className="shop-product-actions"><button className="shop-secondary small" disabled={busy} onClick={onSave}>Save</button><button className="shop-secondary small" disabled={busy} onClick={onToggle}>{product.is_available?"Hide":"Show"}</button><label className="shop-upload-button">Add photos<input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e=>{const files=e.currentTarget.files;onUpload(files);e.currentTarget.value="";}} disabled={busy}/></label></div></article>}
