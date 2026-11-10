/**
 * AgentOS Observatory - Lightweight Privacy-Friendly Web Telemetry Probe (v1)
 * Schema: agentos.web-telemetry/v1
 * Size: < 1KB, No Cookies, Respects DNT (Do Not Track)
 */
(function(window, document) {
  'use strict';

  if (navigator.doNotTrack === '1' || window.doNotTrack === '1') {
    return; // 尊重瀏覽器防追蹤設定
  }

  var ENDPOINT = window.__AGENTOS_TELEMETRY_ENDPOINT__ || '/api/telemetry/v1/event';
  var SITE_ID = window.__AGENTOS_SITE_ID__ || (window.location.hostname || 'unknown');

  function sendEvent(type, data) {
    var payload = {
      schema: 'agentos.web-telemetry/v1',
      site_id: SITE_ID,
      event_type: type || 'pageview',
      path: window.location.pathname,
      search: window.location.search,
      referrer: document.referrer || null,
      screen_width: window.innerWidth || null,
      screen_height: window.innerHeight || null,
      timestamp: new Date().toISOString(),
      metadata: data || {}
    };

    var blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, blob);
    } else {
      fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(function() {});
    }
  }

  // 1. 發送頁面瀏覽事件 (PageView)
  if (document.readyState === 'complete') {
    sendEvent('pageview');
  } else {
    window.addEventListener('load', function() {
      sendEvent('pageview', {
        load_time_ms: window.performance && window.performance.timing ?
          (Date.now() - window.performance.timing.navigationStart) : null
      });
    });
  }

  // 暴露全域自訂事件發送介面
  window.AgentOSTelemetry = {
    track: function(eventName, customData) {
      sendEvent(eventName, customData);
    }
  };
})(window, document);
