(function () {
  if (navigator.doNotTrack === '1' || window.doNotTrack === '1' || navigator.globalPrivacyControl) return;
  try { if (localStorage.getItem('readerfold.excludeOwnTraffic') === '1') return; } catch { /* Optional storage. */ }
  const script = document.querySelector('script[data-resource-path]');
  if (!script || !script.dataset.api) return;
  let source = 'direct';
  try {
    const host = new URL(document.referrer).hostname;
    const match = domain => host === domain || host.endsWith('.'+domain);
    if (!match(location.hostname) && !match('roundtable.works')) {
      source = 'other';
      const sources = {google:['google.com','google.co.uk','google.ca','google.com.au','google.de','google.fr','google.co.in'],bing:['bing.com'],'other-search':['duckduckgo.com','search.yahoo.com','search.brave.com','baidu.com'],chatgpt:['chatgpt.com','chat.openai.com'],perplexity:['perplexity.ai'],claude:['claude.ai'],gemini:['gemini.google.com'],copilot:['copilot.microsoft.com'],social:['facebook.com','instagram.com','t.co','x.com','reddit.com','linkedin.com','youtube.com']};
      for (const [key, domains] of Object.entries(sources)) if (domains.some(match)) { source=key; break; }
    }
  } catch { /* No referrer. */ }
  function send(event) {
    fetch(script.dataset.api+'/analytics/events', {method:'POST',credentials:'include',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({path:script.dataset.resourcePath,event,source})}).catch(()=>{});
  }
  // The API also excludes authenticated owner sessions. No question text or raw referrer is sent.
  send('pageview');
  document.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');
    if (link && new URL(link.href).origin === location.origin && new URL(link.href).pathname.replace(/\/$/,'') === '/signup') send('signup_click');
  });
})();
