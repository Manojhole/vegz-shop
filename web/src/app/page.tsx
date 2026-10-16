const portal = "shop";
const titles: Record<string, string> = {
  user: "Fresh groceries, delivered simply.",
  shop: "Your store, in control.",
  agent: "Every delivery, one clear route.",
  admin: "Vegz platform operations.",
};

export default function HomePage() {
  return <main className="shell"><header><span className="mark">V</span><strong>vegz<span>.</span></strong><span className="portal">{portal} portal</span></header><section className="hero"><p className="eyebrow">THE VEGZ PLATFORM</p><h1>{titles[portal]}</h1><p className="intro">A modern, responsive portal built with Next.js and TypeScript, connected to Vegz FastAPI services.</p><div className="status"><span className="dot" /> Web foundation ready <span className="tag">Next.js · TypeScript</span></div><p className="note">Migration foundation only: existing workflows remain in the current app until their API-backed screens are ported and tested.</p></section><footer>Vegz · Fresh choices. Smarter delivery.</footer></main>;
}
