// Host-neutral: the host supplies lifecycle; this element never starts agents.
class PingPongAnimation extends HTMLElement {
  static get observedAttributes() { return ['status', 'disabled']; }

  constructor() {
    super();
    this.attachShadow({mode: 'open'}).innerHTML = `
      <style>
        :host { display:inline-block; color:inherit; font:12px system-ui,sans-serif; }
        .sprite { display:block; width:192px; height:72px; }
        [hidden] { display:none !important; }
        label { display:flex; align-items:center; gap:6px; cursor:pointer; }
        input { accent-color:#df6958; }
        svg { overflow:visible; image-rendering:pixelated; }
        .ball { transform:translate(18px,14px); }
        .playing .ball { animation:volley 1.6s linear infinite; }
        .playing .left { animation:left-hit 1.6s steps(2,end) infinite; }
        .playing .right { animation:right-hit 1.6s steps(2,end) infinite; }
        @keyframes volley {
          0%,100% { transform:translate(18px,14px); }
          25% { transform:translate(46px,5px); }
          50% { transform:translate(74px,14px); }
          75% { transform:translate(46px,23px); }
        }
        @keyframes left-hit { 0%,94%,100% { transform:translateX(2px); } 8%,90% { transform:translateX(0); } }
        @keyframes right-hit { 0%,42%,58%,100% { transform:translateX(0); } 48%,52% { transform:translateX(-2px); } }
        @media(prefers-reduced-motion:reduce) { .playing * { animation:none !important; } }
      </style>
      <svg class="sprite" viewBox="0 0 96 36" role="img" aria-label="Two pixel paddles exchanging a ball" shape-rendering="crispEdges">
        <g class="left">
          <path fill="#704939" d="M8 23h4v9H8z"/>
          <path fill="#d9584b" d="M6 6h8v2h2v2h2v12h-2v2h-2v2H6v-2H4v-2H2V10h2V8h2z"/>
          <path fill="#f89574" d="M6 8h6v2H6v4H4v-4h2z"/>
        </g>
        <g class="right">
          <path fill="#704939" d="M84 23h4v9h-4z"/>
          <path fill="#5d86b5" d="M82 6h8v2h2v2h2v12h-2v2h-2v2h-8v-2h-2v-2h-2V10h2V8h2z"/>
          <path fill="#9bbddb" d="M82 8h6v2h-6v4h-2v-4h2z"/>
        </g>
        <g class="ball"><path fill="#f3c36b" d="M1 0h2v1h1v2H3v1H1V3H0V1h1z"/><path fill="#fff0cf" d="M1 0h2v1H1z"/></g>
      </svg>
      <label><input type="checkbox" checked>Animation</label>`;
    this.toggle = this.shadowRoot.querySelector('input');
    this.sprite = this.shadowRoot.querySelector('svg');
    this.toggle.addEventListener('change', () => {
      this.enabled = this.toggle.checked;
      this.dispatchEvent(new CustomEvent('animation-preference', {
        detail: {enabled: this.enabled}, bubbles: true, composed: true
      }));
    });
  }

  get enabled() { return !this.hasAttribute('disabled'); }
  set enabled(value) { this.toggleAttribute('disabled', !value); }
  get status() { return this.getAttribute('status') || 'idle'; }
  set status(value) { this.setAttribute('status', value); }
  connectedCallback() { this.render(); }
  disconnectedCallback() { this.sprite.classList.remove('playing'); }
  attributeChangedCallback() { this.render(); }
  render() {
    const running = this.isConnected && this.enabled && this.status === 'running';
    this.toggle.checked = this.enabled;
    this.sprite.toggleAttribute('hidden', !running);
    this.sprite.classList.toggle('playing', running);
  }
}
customElements.define('ping-pong-animation', PingPongAnimation);
