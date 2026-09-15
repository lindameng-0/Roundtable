// Paddle's public client token is safe in the browser. API keys remain server-side.
let loading;
let initializedToken;

export async function initializePaddle(catalog) {
  if (!catalog?.client_token) throw new Error("Payments are not configured");
  if (!window.Paddle) {
    if (!loading) {
      loading = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
        script.async = true;
        const timer = window.setTimeout(() => { script.remove(); loading = null; reject(new Error("Checkout took too long to load")); }, 15000);
        script.onload = () => { window.clearTimeout(timer); resolve(); };
        script.onerror = () => { window.clearTimeout(timer); script.remove(); loading = null; reject(new Error("Could not load checkout")); };
        document.head.appendChild(script);
      });
    }
    await loading;
  }
  if (initializedToken !== catalog.client_token) {
    if (catalog.environment === "sandbox") window.Paddle.Environment.set("sandbox");
    window.Paddle.Initialize({
      token: catalog.client_token,
      checkout: { settings: { displayMode: "overlay", theme: "light", allowLogout: false,
        showAddDiscounts: false, successUrl: `${window.location.origin}/billing?checkout=success` } },
      eventCallback: (event) => window.dispatchEvent(new CustomEvent("roundtable-checkout", { detail: event.name })),
    });
    initializedToken = catalog.client_token;
  }
}

export async function openPaddleCheckout(catalog, transactionId) {
  if (!transactionId) throw new Error("No checkout transaction was supplied");
  await initializePaddle(catalog);
  window.Paddle.Checkout.open({
    transactionId,
    settings: { displayMode: "overlay", theme: "light", locale: "en",
      successUrl: `${window.location.origin}/billing?checkout=success`,
      allowLogout: false, showAddDiscounts: false, allowDiscountRemoval: false },
  });
}
