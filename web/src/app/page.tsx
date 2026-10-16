const API_ORIGIN = (process.env.NEXT_PUBLIC_VEGZ_SHOP_API_URL || "http://localhost:8002").replace(/\/$/, "");

export default function ShopHomePage() {
  return (
    <main className="portal-shell">
      <header className="portal-header">
        <a className="brand" href="/" aria-label="Vegz shop home"><span className="brand-mark">V</span><span>vegz<span className="period">.</span></span></a>
        <span className="portal-label">SHOP PARTNER</span>
        <a className="open-link" href={API_ORIGIN} target="_blank" rel="noreferrer">Open dashboard separately ↗</a>
      </header>
      <section className="portal-intro">
        <p className="eyebrow">YOUR STORE, IN CONTROL</p>
        <h1>Manage the market.<br /><span>Serve your neighbourhood.</span></h1>
        <p>Products, stock, shop availability and incoming orders are provided by the existing FastAPI shop service while the dashboard is migrated into Next.js.</p>
      </section>
      <section className="live-portal">
        <div className="portal-bar"><span className="live-dot" /> <strong>Live shop workspace</strong><span className="portal-origin">{API_ORIGIN}</span></div>
        <iframe title="Vegz Shop dashboard" src={API_ORIGIN} loading="eager" />
      </section>
      <footer>Vegz Shop · Android app uses the same FastAPI shop endpoints.</footer>
    </main>
  );
}
