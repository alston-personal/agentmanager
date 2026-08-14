/**
 * AgentOS Thumbnail Picker
 * Dependency-free Web Component for choosing named visual resources.
 *
 * picker.items = [{ id: 'yuna', name: 'Yuna', thumbnail: '/yuna.jpg' }]
 * picker.addEventListener('change', (event) => console.log(event.detail))
 */
(class AgentOSThumbnailPicker extends HTMLElement {
  constructor() {
    super();
    this._items = [];
    this._value = '';
    this.attachShadow({ mode: 'open' });
  }
  get items() { return this._items; }
  set items(value) {
    this._items = Array.isArray(value) ? value : [];
    if (!this._items.some((item) => String(item.id) === String(this._value))) this._value = this._items[0]?.id || '';
    this.render();
  }
  get value() { return this._value; }
  set value(value) { this._value = value == null ? '' : String(value); this.render(); }
  connectedCallback() { this.render(); }
  render() {
    const selected = this._items.find((item) => String(item.id) === String(this._value));
    this.shadowRoot.innerHTML = `<style>:host{display:block;position:relative;color:#f3f5fa;font:14px system-ui,sans-serif}button{font:inherit;color:inherit;box-sizing:border-box}.trigger{width:100%;display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid #5968a0;border-radius:8px;background:#0f1420;cursor:pointer;text-align:left}.trigger:hover{border-color:#8175ff}.trigger img,.option img{object-fit:cover;border-radius:6px;background:#191e2a}.trigger img{width:42px;height:42px}.name{flex:1}.menu{position:absolute;z-index:20;top:calc(100% + 5px);left:0;right:0;max-height:300px;overflow:auto;padding:6px;border:1px solid #5968a0;border-radius:10px;background:#111827;box-shadow:0 14px 30px #0008}.menu[hidden]{display:none}.option{width:100%;display:flex;align-items:center;gap:10px;padding:8px;border:0;border-radius:7px;background:transparent;cursor:pointer;text-align:left}.option:hover,.option[aria-selected=true]{background:#292752}.option img{width:48px;height:48px}.empty{padding:10px;color:#9eabc3}</style><button class="trigger" type="button" aria-haspopup="listbox" aria-expanded="false"><img alt=""><span class="name"></span><span aria-hidden="true">⌄</span></button><div class="menu" role="listbox" hidden></div>`;
    const trigger = this.shadowRoot.querySelector('.trigger');
    const menu = this.shadowRoot.querySelector('.menu');
    const image = this.shadowRoot.querySelector('.trigger img');
    const name = this.shadowRoot.querySelector('.name');
    name.textContent = selected?.name || this.getAttribute('placeholder') || 'Select an item';
    image.src = selected?.thumbnail || '';
    image.hidden = !selected?.thumbnail;
    for (const item of this._items) {
      const option = document.createElement('button');
      option.type = 'button'; option.className = 'option'; option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', String(String(item.id) === String(this._value)));
      if (item.thumbnail) { const optionImage = document.createElement('img'); optionImage.src = item.thumbnail; optionImage.alt = ''; option.append(optionImage); }
      const label = document.createElement('span'); label.textContent = item.name || item.id; option.append(label); menu.append(option);
      option.addEventListener('click', () => { this._value = String(item.id); menu.hidden = true; trigger.setAttribute('aria-expanded', 'false'); this.render(); this.dispatchEvent(new CustomEvent('change', { bubbles: true, detail: item })); });
    }
    if (!this._items.length) { const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = 'No items'; menu.append(empty); }
    trigger.addEventListener('click', () => { menu.hidden = !menu.hidden; trigger.setAttribute('aria-expanded', String(!menu.hidden)); });
  }
})()
