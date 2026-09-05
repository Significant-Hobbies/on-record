// App Health browser logs. Public, origin-pinned key; nothing here is secret.
// Logs form submits, clicks on [data-log] elements, and client errors to the
// Logs tab at health.sassmaker.com. window.appHealthLog(event, options) is
// available for custom events. Source: app-health/examples/dropin-log-client.
(() => {
  const KEY = 'ahk_pub_9b337aa5b9aa5202dd5319ebcac3a5feab6036c66933323d',
    ENV = 'production',
    URL = 'https://ingest.sassmaker.com/v1/logs';
  function id() {
    return crypto.randomUUID();
  }
  function send(event, opts) {
    const o = opts || {};
    const props = {},
      src = o.props || {};
    for (const k in src) {
      if (src[k] !== undefined) {
        props[k] = typeof src[k] === 'string' ? src[k].slice(0, 500) : src[k];
      }
    }
    const body = JSON.stringify({
      public_key: KEY,
      batch_id: id(),
      schema_version: 'v1',
      environment: ENV,
      logs: [
        {
          log_id: id(),
          timestamp: Date.now(),
          event,
          level: o.level || 'info',
          title: o.title,
          description: o.description,
          icon: o.icon,
          props,
        },
      ],
    });
    if (document.visibilityState === 'hidden' && navigator.sendBeacon) {
      navigator.sendBeacon(URL, new Blob([body], { type: 'text/plain' }));
      return;
    }
    fetch(URL, {
      method: 'POST',
      headers: { 'content-type': 'text/plain' },
      body,
      keepalive: true,
    }).catch(() => undefined);
  }
  window.appHealthLog = send;
  document.addEventListener(
    'submit',
    (e) => {
      const f = e.target;
      if (!f || f.tagName !== 'FORM') {
        return;
      }
      send('form.submitted', {
        title: f.id || f.getAttribute('name') || f.getAttribute('action') || 'form',
        props: { page: location.pathname },
      });
    },
    true
  );
  document.addEventListener(
    'click',
    (e) => {
      const t = e.target && e.target.closest ? e.target.closest('[data-log]') : null;
      const name = t && t.getAttribute('data-log');
      if (name) {
        send(name, {
          title: (t.textContent || '').trim().slice(0, 120) || name,
          props: { page: location.pathname },
        });
      }
    },
    true
  );
  window.addEventListener('error', (e) => {
    send('client.error', {
      level: 'error',
      title: String(e.message || 'error').slice(0, 200),
      props: { page: location.pathname },
    });
  });
  window.addEventListener('unhandledrejection', (e) => {
    const r = e.reason && e.reason.message ? e.reason.message : String(e.reason);
    send('client.error', {
      level: 'error',
      title: r.slice(0, 200),
      props: { page: location.pathname, kind: 'rejection' },
    });
  });
})();
