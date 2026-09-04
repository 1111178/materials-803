/* phase_lab_ui.js —— 相图实验室本地渲染组件入口(浏览器内全交互,零服务器往返)。
 * 前置拼接 phase_lab_core.js(经 global.LabCore 暴露 classify / fecRoomReadout)。
 *
 * 交互模型:
 *   - 拖动滑块 / 点开关 / 切体系 / Fe-C 预置:全在本地即时重画(requestAnimationFrame),不上报;
 *   - 唯一上报时机:① <select> 换体系 → 服务器刷新下方"对照知识点卡";② 滑块松手(change)/预置点击
 *     → 记住该体系当前成分/温度(导航回来不丢)。上报值与服务器已有值一致时静默跳过(避免死循环)。
 *
 * spec 由 phase_lab.system_spec(sid) 导出,与后端判相/杠杆同源同数值。
 */
export default function (component) {
  'use strict';
  var root = (component && component.parentElement) || null;
  if (!root) return;
  var data = (component && component.data) || {};
  var Lab = (typeof globalThis !== 'undefined' && globalThis.LabCore) || {};

  var order = data.order || [];
  var specs = data.specs || {};
  var active = data.active || order[0] || '';
  if (!specs[active] && order.length) active = order[0];
  var spec = specs[active] || {};
  var pos = data.pos || {};

  // 每体系独立记住的成分/温度;无记忆时用该体系 default
  function curFor(sid) {
    var s = specs[sid]; if (!s) return { x: 0, T: 25 };
    var p = pos[sid]; var d = s.default || {};
    return { x: (p && p.x != null) ? p.x : d.x, T: (p && p.T != null) ? p.T : d.T };
  }
  var st = curFor(active);
  if (st.x == null) st.x = spec.default ? spec.default.x : 0;
  if (st.T == null) st.T = spec.default ? spec.default.T : 25;
  var xD = spec.x_domain || [0, 1];
  var tD = spec.t_domain || [0, 1];
  st.x = Math.max(xD[0], Math.min(xD[1], st.x));
  st.T = Math.max(tD[0], Math.min(tD[1], st.T));

  // 显示开关(默认全开,与旧版一致)
  var o = { fill: true, grid: true, keys: true, cross: true, inv: true };

  // ================= 颜色 =================
  var C = {
    bg: '#1B2F52', grid: '#2C4268', axis: '#D6E2F0', gold: '#FFD166',
    pink: '#F15FA6', solid: '#7FB3F0', page: '#EDF3E8',
    ink: '#41534A', dim: '#7A8698', card: 'rgba(255,255,255,0.74)',
    border: '#DFEAD4', green: '#83B57C', darkInk: '#10213A'
  };

  function hexA(hex, a) {
    var r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }

  // ================= 数值格式化(镜像 python %g / %.1f / %.4g / %.3g)=================
  function trim(v) {
    var n = Number(v);
    if (!isFinite(n)) return String(v);
    if (n === 0) return '0';
    if (Math.abs(n) >= 1000) return String(Math.round(n));
    var s = n.toPrecision(12);
    return String(parseFloat(s));
  }
  function fmtG(v, p) { // ~python "%.{p}g"
    var n = Number(v);
    if (!isFinite(n)) return String(v);
    if (n === 0) return '0';
    var s = n.toPrecision(p);
    if (s.indexOf('e') !== -1) return String(parseFloat(s));
    return String(parseFloat(s));
  }
  function fmtPct(v) { return (Math.round(Number(v) * 10) / 10).toFixed(1); }
  function fmt3(v) { var s = Number(v).toFixed(3); return s; }
  function fmt0(v) { return String(Math.round(Number(v))); }

  function decStep(s) { return s && s.fec ? '0.01' : '1'; }
  function fmtVal(v, s) { return s && s.fec ? fmt3(v) : fmt0(v); }

  // ================= 布局 =================
  root.innerHTML = '';
  var STYLE = '' +
    'html,body{margin:0;padding:0;height:100%;background:' + C.page + ';overflow:hidden;}' +
    '.plr{font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;color:#26362E;box-sizing:border-box;' +
    'width:100%;height:100vh;overflow:hidden;display:flex;flex-direction:column;}' +
    '.plr *{box-sizing:border-box;}' +
    /* 控制区(奶白圆角盒,与页面其它控件容器一致) */
    '.ctrl{background:rgba(255,255,255,0.72);border:1px solid ' + C.border + ';border-radius:14px;padding:8px 12px 6px;margin:0 0 8px;flex:0 0 auto;}' +
    '.l1{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;}' +
    '.sysbox{display:flex;align-items:center;gap:7px;}' +
    '.sysbox .cap{font-size:12px;color:' + C.dim + ';white-space:nowrap;}' +
    '.sel{font-family:inherit;font-size:14px;font-weight:700;color:#10213A;background:#fff;border:1px solid #C7D9C0;' +
    'border-radius:9px;padding:5px 10px;outline:none;cursor:pointer;max-width:230px;}' +
    '.toggles{display:flex;flex-wrap:wrap;align-items:center;gap:2px 14px;}' +
    '.tog{display:flex;align-items:center;gap:5px;font-size:13px;color:' + C.ink + ';cursor:pointer;user-select:none;}' +
    '.tog input{width:15px;height:15px;accent-color:' + C.green + ';cursor:pointer;margin:0;}' +
    '.tagchip{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;margin-left:auto;white-space:nowrap;}' +
    '.l2{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px;}' +
    '.l2 .precap{font-size:12px;color:' + C.dim + ';white-space:nowrap;}' +
    '.chip{border:1px solid #C7D9C0;background:#F3F8EF;color:#2E5B33;font-size:12px;font-weight:700;' +
    'border-radius:999px;padding:3px 11px;cursor:pointer;transition:background .12s, transform .05s;}' +
    '.chip:hover{background:#E3F0DA;}' +
    '.chip:active{transform:translateY(1px);}' +
    /* 滑块行 */
    '.sl{display:flex;gap:18px;flex-wrap:wrap;margin:0 0 8px;flex:0 0 auto;}' +
    '.slit{flex:1 1 260px;min-width:230px;display:flex;flex-direction:column;gap:2px;}' +
    '.slab{display:flex;justify-content:space-between;font-size:12px;color:' + C.ink + ';}' +
    '.slab b{font-size:12px;color:#10213A;font-weight:700;}' +
    'input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:22px;background:transparent;cursor:pointer;}' +
    'input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:3px;background:#C9D8C2;}' +
    'input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:17px;height:17px;border-radius:50%;' +
    'background:#fff;border:3px solid ' + C.green + ';margin-top:-5.5px;box-shadow:0 1px 3px rgba(30,60,40,.25);}' +
    'input[type=range]::-moz-range-track{height:6px;border-radius:3px;background:#C9D8C2;}' +
    'input[type=range]::-moz-range-thumb{width:13px;height:13px;border-radius:50%;background:#fff;border:3px solid ' + C.green + ';}' +
    /* 主区:左图右读数 */
    '.main{display:flex;gap:12px;align-items:stretch;flex:1 1 auto;min-height:0;}' +
    '.leftcol{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;}' +
    '.cc{position:relative;flex:1 1 auto;min-height:300px;background:' + C.bg + ';border-radius:14px;overflow:hidden;' +
    'border:1px solid #132A4E;box-shadow:0 4px 14px rgba(27,47,82,.18);}' +
    '.cc canvas{position:absolute;inset:0;width:100%;height:100%;display:block;}' +
    '.note{margin-top:5px;font-size:12px;color:' + C.dim + ';line-height:1.5;}' +
    '.rc{flex:0 0 332px;min-width:280px;max-height:100%;overflow-y:auto;padding-right:2px;}' +
    '.rc::-webkit-scrollbar{width:8px;}.rc::-webkit-scrollbar-thumb{background:#C9D8C2;border-radius:4px;}' +
    /* 读数卡 */
    '.k{background:' + C.card + ';border:1px solid ' + C.border + ';border-left:4px solid ' + C.green + ';' +
    'border-radius:12px;padding:8px 11px;margin:0 0 8px;}' +
    '.kt{font-size:12px;color:' + C.dim + ';margin-bottom:4px;}' +
    '.pill{display:inline-block;padding:1px 11px;border-radius:999px;font-weight:700;font-size:13px;' +
    'color:' + C.darkInk + ';border:1px solid rgba(0,0,0,.08);margin-right:5px;}' +
    '.kb{font-size:15px;font-weight:800;color:' + C.ink + ';}' +
    '.ktxt{font-size:13px;color:' + C.ink + ';line-height:1.8;}' +
    '.ktxt b{color:#10213A;}' +
    '.ktxt .hint{color:' + C.dim + ';font-size:12px;}' +
    '.legend{font-size:13px;color:' + C.ink + ';margin-top:6px;}' +
    '.legend .row{display:flex;align-items:center;gap:8px;margin:2px 0;}' +
    '.legend .sw{width:14px;height:14px;border-radius:4px;flex:none;}' +
    '.legend .nm{flex:1;}' +
    '.legend .vv{font-weight:700;}' +
    '.bar{display:flex;height:20px;border-radius:8px;overflow:hidden;border:1px solid #D5E3CD;}' +
    '.bar .cell{height:20px;}' +
    '.bar .none{width:100%;background:#dfe8d4;height:20px;}' +
    '@media (max-width:860px){ .main{flex-direction:column;} .rc{flex:0 0 auto;max-height:none;overflow:visible;} }';
  var styleEl = document.createElement('style');
  styleEl.textContent = STYLE;
  root.appendChild(styleEl);

  var wrap = document.createElement('div');
  wrap.className = 'plr';
  root.appendChild(wrap);

  // --- 控制区 ---
  var ctrl = document.createElement('div'); ctrl.className = 'ctrl';
  var l1 = document.createElement('div'); l1.className = 'l1';
  var sysbox = document.createElement('div'); sysbox.className = 'sysbox';
  sysbox.innerHTML = '<span class="cap">二元体系</span>';
  var sel = document.createElement('select'); sel.className = 'sel';
  for (var si = 0; si < order.length; si++) {
    var opt = document.createElement('option');
    opt.value = order[si];
    opt.textContent = order[si];
    if (order[si] === active) opt.selected = true;
    sel.appendChild(opt);
  }
  sysbox.appendChild(sel);
  var toggles = document.createElement('div'); toggles.className = 'toggles';
  var TOG = [['fill', '相区+标签'], ['grid', '网格'], ['keys', '关键点字母'], ['cross', '光标+杠杆'], ['inv', '反应标注']];
  for (var ti = 0; ti < TOG.length; ti++) {
    (function (key, label) {
      var lb = document.createElement('label'); lb.className = 'tog';
      var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true;
      cb.addEventListener('change', function () { o[key] = cb.checked; redraw(); });
      var sp = document.createElement('span'); sp.textContent = label;
      lb.appendChild(cb); lb.appendChild(sp); toggles.appendChild(lb);
    })(TOG[ti][0], TOG[ti][1]);
  }
  l1.appendChild(sysbox); l1.appendChild(toggles);
  ctrl.appendChild(l1);

  // 右上角 数值权威/教学近似 小标(放控制行最右)
  var chip = document.createElement('span');
  chip.className = 'tagchip';
  if (spec.exact) { chip.textContent = '✓ 数值权威'; chip.style.background = '#E0F2DA'; chip.style.color = '#2E5B33'; }
  else { chip.textContent = '⚠ 教学近似'; chip.style.background = '#FBEBD0'; chip.style.color = '#8A5A17'; }
  l1.appendChild(chip);

  // Fe-C 预置 chip 行
  var presRow = document.createElement('div'); presRow.className = 'l2'; presRow.style.display = 'none';
  var precap = document.createElement('span'); precap.className = 'precap';
  precap.textContent = '一键跳到标准钢种 / 铸铁(拉到室温 25℃):';
  presRow.appendChild(precap);
  var pres = spec.presets || [];
  for (var pi = 0; pi < pres.length; pi++) {
    (function (label, c0) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'chip';
      b.textContent = label;
      b.title = '成分 → ' + fmtG(c0, 3) + '%C,温度 → 25℃';
      b.addEventListener('click', function () { setProbe(c0, 25, true); });
      presRow.appendChild(b);
    })(pres[pi][0], pres[pi][1]);
  }
  if (spec.fec && pres.length) presRow.style.display = 'flex';
  ctrl.appendChild(presRow);
  wrap.appendChild(ctrl);

  // --- 滑块行 ---
  var slRow = document.createElement('div'); slRow.className = 'sl';
  function buildSlit(which) {
    var s = spec;
    var lit = document.createElement('div'); lit.className = 'slit';
    var labRow = document.createElement('div'); labRow.className = 'slab';
    var labL = document.createElement('span');
    var labV = document.createElement('b');
    if (which === 'x') {
      labL.textContent = s.fec ? '含碳量 w(C) / wt%C' : '成分(' + (s.xlabel || '') + ')';
      labV.textContent = fmtVal(st.x, s);
    } else {
      labL.textContent = '温度 T / ℃';
      labV.textContent = fmtVal(st.T, s);
    }
    labRow.appendChild(labL); labRow.appendChild(labV);
    var inp = document.createElement('input');
    inp.type = 'range';
    if (which === 'x') {
      inp.min = String(xD[0]); inp.max = String(xD[1]); inp.step = decStep(s); inp.value = String(st.x);
    } else {
      inp.min = String(tD[0]); inp.max = String(tD[1]); inp.step = '1'; inp.value = String(st.T);
    }
    inp.addEventListener('input', function () {
      if (which === 'x') { st.x = parseFloat(inp.value); labV.textContent = fmtVal(st.x, s); }
      else { st.T = parseFloat(inp.value); labV.textContent = fmtVal(st.T, s); }
      redraw();
    });
    inp.addEventListener('change', function () { maybeReport(); }); // 松手才上报(持久化)
    lit.appendChild(labRow); lit.appendChild(inp);
    return lit;
  }
  slRow.appendChild(buildSlit('x'));
  slRow.appendChild(buildSlit('T'));
  wrap.appendChild(slRow);

  // --- 主区 ---
  var main = document.createElement('div'); main.className = 'main';
  var leftcol = document.createElement('div'); leftcol.className = 'leftcol';
  var cc = document.createElement('div'); cc.className = 'cc';
  var cv = document.createElement('canvas'); cc.appendChild(cv);
  leftcol.appendChild(cc);
  if (spec.note) {
    var note = document.createElement('div'); note.className = 'note';
    note.innerHTML = 'ℹ️ ' + spec.note;
    leftcol.appendChild(note);
  }
  main.appendChild(leftcol);
  var rc = document.createElement('div'); rc.className = 'rc';
  main.appendChild(rc);
  wrap.appendChild(main);

  // ================= 绘制 =================
  var PAD = { l: 58, r: 16, t: 42, b: 42 };

  function plotBox(cw, ch) {
    return { x0: PAD.l, y0: PAD.t, x1: cw - PAD.r, y1: ch - PAD.b };
  }
  function X(v, box, cw) { var s = spec; return box.x0 + (v - s.x_domain[0]) / (s.x_domain[1] - s.x_domain[0]) * (box.x1 - box.x0); }
  function Y(v, box, ch) { var s = spec; return box.y0 + (s.t_domain[1] - v) / (s.t_domain[1] - s.t_domain[0]) * (box.y1 - box.y0); }

  function niceTicks(minv, maxv, count) {
    if (!(maxv > minv)) return [minv];
    var step0 = (maxv - minv) / Math.max(1, count);
    var mag = Math.pow(10, Math.floor(Math.log(step0) / Math.LN10));
    var norm = step0 / mag;
    var stepN = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
    var step = stepN * mag;
    var start = Math.ceil(minv / step - 1e-9) * step;
    var arr = [];
    for (var v = start; v <= maxv + step * 1e-6; v += step) arr.push(v);
    return arr;
  }

  function polyPath(ctx, poly, box, cw, ch) {
    ctx.beginPath();
    ctx.moveTo(X(poly[0][0], box, cw), Y(poly[0][1], box, ch));
    for (var i = 1; i < poly.length; i++) ctx.lineTo(X(poly[i][0], box, cw), Y(poly[i][1], box, ch));
    ctx.closePath();
  }

  function drawChart() {
    if (!cv.parentNode) return;
    var cw = cc.clientWidth, ch = cc.clientHeight;
    if (cw < 40 || ch < 40) return;
    var dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(cw * dpr) || cv.height !== Math.round(ch * dpr)) {
      cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr);
    }
    var ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, cw, ch);
    var box = plotBox(cw, ch);
    var FONT = '"Segoe UI","Microsoft YaHei",system-ui,sans-serif';

    // 标题
    ctx.fillStyle = C.axis;
    ctx.font = '600 14px ' + FONT;
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillText(spec.title || '', PAD.l - 4, 22);
    ctx.font = '11px ' + FONT;
    ctx.fillStyle = spec.exact ? '#9FD9A4' : '#E7C37B';
    ctx.textAlign = 'right';
    ctx.fillText(spec.exact ? '数值权威' : '教学近似', cw - PAD.r, 22);

    ctx.save();
    ctx.beginPath(); ctx.rect(box.x0, box.y0, box.x1 - box.x0, box.y1 - box.y0); ctx.clip();

    var fontAxis = '11px ' + FONT;
    // 网格
    if (o.grid) {
      var tx = niceTicks(spec.x_domain[0], spec.x_domain[1], 6);
      var ty = niceTicks(spec.t_domain[0], spec.t_domain[1], 7);
      ctx.lineWidth = 1; ctx.strokeStyle = hexA(C.grid, 0.9);
      for (var ix = 0; ix < tx.length; ix++) {
        var gx = X(tx[ix], box, cw);
        ctx.beginPath(); ctx.moveTo(gx, box.y0); ctx.lineTo(gx, box.y1); ctx.stroke();
      }
      for (var iy = 0; iy < ty.length; iy++) {
        var gy = Y(ty[iy], box, ch);
        ctx.beginPath(); ctx.moveTo(box.x0, gy); ctx.lineTo(box.x1, gy); ctx.stroke();
      }
    }
    // 相区填充
    if (o.fill) {
      var regs = spec.regions || [];
      for (var r0 = 0; r0 < regs.length; r0++) {
        polyPath(ctx, regs[r0].poly, box, cw, ch);
        ctx.fillStyle = hexA(regs[r0].fill, 0.7);
        ctx.fill();
      }
    }
    // 边界线
    var lines = spec.lines || [];
    for (var li = 0; li < lines.length; li++) {
      var ln = lines[li], pts = ln.pts || [];
      if (pts.length < 2) continue;
      ctx.beginPath();
      ctx.moveTo(X(pts[0][0], box, cw), Y(pts[0][1], box, ch));
      for (var pi2 = 1; pi2 < pts.length; pi2++) ctx.lineTo(X(pts[pi2][0], box, cw), Y(pts[pi2][1], box, ch));
      ctx.strokeStyle = ln.color || C.solid;
      ctx.lineWidth = ln.w || 2.4;
      ctx.setLineDash(ln.dash === 1 ? [7, 5] : ln.dash === 2 ? [2, 4] : []);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    // 三相水平线
    var invs = spec.invariants || [];
    for (var ii = 0; ii < invs.length; ii++) {
      var inv = invs[ii];
      ctx.beginPath();
      ctx.moveTo(X(inv.x_lo, box, cw), Y(inv.T, box, ch));
      ctx.lineTo(X(inv.x_hi, box, cw), Y(inv.T, box, ch));
      ctx.strokeStyle = C.gold; ctx.lineWidth = 3; ctx.stroke();
      if (o.inv) {
        ctx.font = '12px ' + FONT; ctx.fillStyle = C.pink;
        ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
        var mxx = X((inv.x_lo + inv.x_hi) / 2, box, cw);
        ctx.fillText(inv.txt || '', mxx, Y(inv.T, box, ch) - 2);
      }
    }
    // 相区标签(质心)
    if (o.fill) {
      ctx.font = '600 12px ' + FONT;
      for (var rj = 0; rj < regs.length; rj++) {
        var rg = regs[rj];
        if (rg.name === 'Fe₃C') continue;
        var poly = rg.poly; var cx = 0, cy = 0;
        for (var pp = 0; pp < poly.length; pp++) { cx += poly[pp][0]; cy += poly[pp][1]; }
        cx /= poly.length; cy /= poly.length;
        var px = X(cx, box, cw), py = Y(cy, box, ch);
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        var wtxt = ctx.measureText(rg.name).width;
        ctx.fillStyle = 'rgba(27,47,82,0.5)';
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(px - wtxt / 2 - 4, py - 8, wtxt + 8, 16, 7)
                      : ctx.rect(px - wtxt / 2 - 4, py - 8, wtxt + 8, 16);
        ctx.fill();
        ctx.fillStyle = '#F4F7FB';
        ctx.fillText(rg.name, px, py);
      }
    }
    // 关键点字母
    if (o.keys) {
      var keys = spec.keys || [];
      for (var kk = 0; kk < keys.length; kk++) {
        var kp = keys[kk];
        var kx = X(kp[1], box, cw), ky = Y(kp[2], box, ch);
        ctx.beginPath(); ctx.arc(kx, ky, 3, 0, Math.PI * 2);
        ctx.fillStyle = C.gold; ctx.fill();
        ctx.strokeStyle = C.bg; ctx.lineWidth = 1; ctx.stroke();
        ctx.fillStyle = C.gold; ctx.font = '700 12px ' + FONT;
        ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
        ctx.fillText(String(kp[0]), kx, ky - 4);
      }
    }
    // 光标 + 杠杆
    if (o.cross) {
      var px = X(st.x, box, cw), py = Y(st.T, box, ch);
      ctx.strokeStyle = 'rgba(241,95,166,0.55)'; ctx.lineWidth = 1;
      ctx.setLineDash([3, 4]);
      ctx.beginPath(); ctx.moveTo(px, box.y0); ctx.lineTo(px, box.y1); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(box.x0, py); ctx.lineTo(box.x1, py); ctx.stroke();
      ctx.setLineDash([]);
      var cls = Lab.classify ? Lab.classify(spec, st.x, st.T) : null;
      if (cls && cls.kind === 'two') {
        var ex1 = X(cls.left, box, cw), ex2 = X(cls.right, box, cw);
        ctx.strokeStyle = 'rgba(255,209,102,0.65)'; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(ex1, py); ctx.lineTo(ex2, py); ctx.stroke();
        ctx.font = '10px ' + FONT; ctx.fillStyle = C.axis;
        ctx.textAlign = 'center';
        [[ex1, fmtG(cls.left, 2)], [ex2, fmtG(cls.right, 2)]].forEach(function (e) {
          ctx.beginPath(); ctx.arc(e[0], py, 4, 0, Math.PI * 2);
          ctx.fillStyle = C.gold; ctx.fill();
          ctx.strokeStyle = C.bg; ctx.lineWidth = 1; ctx.stroke();
          ctx.textBaseline = 'top';
          ctx.fillText(e[1], e[0], py + 6);
        });
      }
      // 探针大金点
      ctx.beginPath(); ctx.arc(px, py, 5.5, 0, Math.PI * 2);
      ctx.fillStyle = C.gold; ctx.fill();
      ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.6; ctx.stroke();
    }
    ctx.restore();

    // 坐标轴
    var ax = spec.x_domain[0], ax2 = spec.x_domain[1];
    ctx.strokeStyle = C.axis; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(box.x0, box.y1); ctx.lineTo(box.x1, box.y1); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(box.x0, box.y0); ctx.lineTo(box.x0, box.y1); ctx.stroke();
    ctx.font = fontAxis; ctx.fillStyle = C.axis;
    var tx2 = niceTicks(spec.x_domain[0], spec.x_domain[1], 6);
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (var txi = 0; txi < tx2.length; txi++) {
      var xv = tx2[txi];
      var xtx = X(xv, box, cw);
      ctx.fillText(trim(xv), xtx, box.y1 + 6);
      ctx.beginPath(); ctx.moveTo(xtx, box.y1); ctx.lineTo(xtx, box.y1 + 4); ctx.stroke();
    }
    var ty2 = niceTicks(spec.t_domain[0], spec.t_domain[1], 7);
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (var tyi = 0; tyi < ty2.length; tyi++) {
      var tv = ty2[tyi];
      var yty = Y(tv, box, ch);
      ctx.fillText(trim(tv), box.x0 - 6, yty);
      ctx.beginPath(); ctx.moveTo(box.x0, yty); ctx.lineTo(box.x0 - 4, yty); ctx.stroke();
    }
    // 轴标题
    ctx.font = '12px ' + FONT; ctx.fillStyle = C.axis;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(spec.xlabel || '', (box.x0 + box.x1) / 2, box.y1 + 24);
    ctx.save();
    ctx.translate(14, (box.y0 + box.y1) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(spec.ylabel || '', 0, 0);
    ctx.restore();
  }

  // ================= 读数面板(镜像 python _phlab_readout_col / _phlab_fec_room)=================
  function pill(text, bg) {
    return '<span class="pill" style="background:' + bg + ';border-color:' + bg + 'AA;">' + text + '</span>';
  }
  function card(title, body, accent) {
    return '<div class="k" style="border-left-color:' + (accent || C.green) + ';">' +
           '<div class="kt">' + title + '</div>' + body + '</div>';
  }
  function bar(parts) {
    var cells = '';
    var nonEmpty = false;
    for (var i = 0; i < parts.length; i++) {
      if (parts[i][1] < 0.05) continue;
      nonEmpty = true;
      cells += '<div class="cell" style="width:' + parts[i][1].toFixed(2) + '%;background:' + parts[i][2] + ';" title="' +
               parts[i][0] + ' ' + fmtPct(parts[i][1]) + '%"></div>';
    }
    var body = cells || '<div class="none"></div>';
    return '<div class="bar">' + body + '</div>';
  }
  function legend(parts) {
    var s = '<div class="legend">';
    for (var i = 0; i < parts.length; i++) {
      s += '<div class="row"><span class="sw" style="background:' + parts[i][2] + ';"></span>' +
           '<span class="nm">' + parts[i][0] + '</span>' +
           '<span class="vv">' + fmtPct(parts[i][1]) + '%</span></div>';
    }
    return s + '</div>';
  }
  function phaseColor(name) {
    return (spec.colors && spec.colors[name]) || '#ccc';
  }
  function readSingle(cls) {
    var ph = cls.region || (cls.phases && cls.phases[0]) || '';
    var col = phaseColor(ph);
    var note = cls.text || (spec.phname && spec.phname[ph]) || ph;
    if (ph === 'L') note = '全部熔化 → 单一液相';
    return card('① 当前状态',
      pill(ph, col) + ' <span class="kb">单相区</span>' +
      '<div class="ktxt hint" style="margin-top:5px;">' + note + '</div>');
  }
  function readTwo(cls) {
    var ph0 = cls.phases[0], ph1 = cls.phases[1] || '';
    var c0 = phaseColor(ph0), c1 = phaseColor(ph1);
    var w0 = cls.w_left * 100, w1 = cls.w_right * 100;
    var head = pill(ph0, c0) + pill(ph1, c1) + ' <span class="kb">两相区</span>';
    var body = '<div class="ktxt">tie line 两端成分:左端 <b>' + ph0 + ' = ' + fmtG(cls.left, 4) + '</b>,' +
               '右端 <b>' + ph1 + ' = ' + fmtG(cls.right, 4) + '</b> (对应图中金色圆点)。' +
               '<br><b>W(' + ph1 + ')</b> = (x − x₁)/(x₂ − x₁) = ' + fmtPct(w1) + '%' +
               '<br><b>W(' + ph0 + ')</b> = 1 − W(' + ph1 + ') = ' + fmtPct(w0) + '%</div>';
    return card('① 当前状态', head) +
           card('② 杠杆定律(等温线 T=' + fmtG(st.T, 4) + '℃)', body, '#FFD166') +
           card('③ 相相对量(x=' + fmtG(st.x, 4) + ')',
                bar([[ph0, w0, c0], [ph1, w1, c1]]) + legend([[ph0, w0, c0], [ph1, w1, c1]]), '#F15FA6');
  }
  function readInv(cls) {
    return card('⭐ 三相平衡线(无杠杆)',
      '<div class="ktxt" style="font-weight:700;font-size:15px;">' + cls.text + '</div>' +
      '<div class="ktxt hint" style="margin-top:4px;">此处恰好落在水平线上,三相共存,杠杆定律不适用。</div>', '#F15FA6');
  }
  // Fe-C 室温组织(镜像 python _phlab_fec_room)
  function fecRoom(x) {
    if (x >= 6.68) {
      return card('室温(25℃)',
        pill('Fe₃C', phaseColor('Fe₃C')) +
        '<span class="ktxt" style="font-weight:800;margin-left:4px;">纯渗碳体(6.69%C)</span>' +
        '<div class="ktxt hint" style="margin-top:4px;">成分已达渗碳体成分,组织 = 相 = Fe₃C。</div>', '#F15FA6');
    }
    var ro = Lab.fecRoomReadout ? Lab.fecRoomReadout(x, spec) : null;
    if (!ro) return '';
    // core 返回 [{name,frac,col}];bar/legend 要 [name, w, color] 三元组
    function arr(list) {
      var a = [];
      for (var i = 0; i < list.length; i++) a.push([list[i].name, list[i].frac, list[i].col]);
      return a;
    }
    var s = '';
    s += card('材料类别 · 此成分室温平衡组织(' + fmtG(x, 3) + '%C)',
              pill(ro.cls, '#BBD5F2'));
    s += card('组织组成物', bar(arr(ro.org)) + legend(arr(ro.org)) + '<div class="ktxt hint" style="margin-top:4px;">' + ro.tags + '</div>', '#FFD166');
    s += card('相组成物(室温)', bar(arr(ro.ph)) + legend(arr(ro.ph)) + '<div class="ktxt hint" style="margin-top:4px;">公式:W(Fe₃C)=(C₀−0.0008)/(6.69−0.0008)</div>', '#F15FA6');
    return s;
  }
  function readout() {
    if (!spec.regions) return;
    var cls = Lab.classify ? Lab.classify(spec, st.x, st.T) : { kind: 'single', region: '' };
    var s = '';
    if (cls.kind === 'two') s += readTwo(cls);
    else if (cls.kind === 'invariant') s += readInv(cls);
    else s += readSingle(cls);
    if (spec.fec) { s += '<div style="border-top:1px dashed ' + C.border + ';margin:10px 0;"></div>' + fecRoom(st.x); }
    rc.innerHTML = s;
  }

  function redraw() {
    drawChart();
    readout();
  }

  // ================= 探针设置 + 上报 =================
  function setProbe(x, T, fire) {
    x = Math.max(xD[0], Math.min(xD[1], x));
    T = Math.max(tD[0], Math.min(tD[1], T));
    st.x = x; st.T = T;
    var sls = slRow.querySelectorAll('input[type=range]');
    if (sls[0]) sls[0].value = String(x);
    if (sls[1]) sls[1].value = String(T);
    redraw();
    if (fire) maybeReport();
  }

  var lastSent = { sid: active, x: st.x, T: st.T };
  function maybeReport() {
    if (typeof component.setTriggerValue !== 'function') return;
    var sid = active, x = st.x, T = st.T;
    var changed = false;
    if (sid !== lastSent.sid) { try { component.setTriggerValue('sid', sid); } catch (e) { /* noop */ } changed = true; }
    if (x !== lastSent.x) { try { component.setTriggerValue('x', x); } catch (e) { /* noop */ } changed = true; }
    if (T !== lastSent.T) { try { component.setTriggerValue('T', T); } catch (e) { /* noop */ } changed = true; }
    if (changed) lastSent = { sid: sid, x: x, T: T };
  }

  // 切体系:本地即时换 spec,仅当真的不同才上报(服务器据此刷下方知识卡)
  sel.addEventListener('change', function () {
    var nsid = sel.value;
    if (!specs[nsid]) return;
    active = nsid;
    spec = specs[nsid];
    xD = spec.x_domain; tD = spec.t_domain;
    var nst = curFor(nsid);
    st.x = Math.max(xD[0], Math.min(xD[1], nst.x));
    st.T = Math.max(tD[0], Math.min(tD[1], nst.T));
    // 顶部控件换样式:预设行显隐、label 文案、数值权威小标、note
    chip.textContent = spec.exact ? '✓ 数值权威' : '⚠ 教学近似';
    chip.style.background = spec.exact ? '#E0F2DA' : '#FBEBD0';
    chip.style.color = spec.exact ? '#2E5B33' : '#8A5A17';
    // note 行重建
    var oldNote = leftcol.querySelector('.note');
    if (oldNote) oldNote.remove();
    if (spec.note) {
      var n2 = document.createElement('div'); n2.className = 'note';
      n2.innerHTML = 'ℹ️ ' + spec.note;
      leftcol.appendChild(n2);
    }
    presRow.innerHTML = '';
    precap.textContent = '一键跳到标准钢种 / 铸铁(拉到室温 25℃):';
    presRow.appendChild(precap);
    var np = spec.presets || [];
    for (var i = 0; i < np.length; i++) {
      (function (label, c0) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'chip';
        b.textContent = label;
        b.title = '成分 → ' + fmtG(c0, 3) + '%C,温度 → 25℃';
        b.addEventListener('click', function () { setProbe(c0, 25, true); });
        presRow.appendChild(b);
      })(np[i][0], np[i][1]);
    }
    presRow.style.display = (spec.fec && np.length) ? 'flex' : 'none';
    // 滑块重建
    slRow.innerHTML = '';
    slRow.appendChild(buildSlit('x'));
    slRow.appendChild(buildSlit('T'));
    redraw();
    maybeReport(); // 与旧 lastSent(sid) 不同 → 上报 sid,触发服务器刷新下方知识卡
  });

  // ================= 启动 =================
  var raf = null;
  function schedule() {
    if (raf) return;
    raf = requestAnimationFrame(function () { raf = null; redraw(); });
  }
  if (window.ResizeObserver) {
    // 每个 run 重画一次 DOM,RO 目标会变——只留一个活跃 observer,避免监听器越叠越多。
    if (globalThis.__m803labRO) { try { globalThis.__m803labRO.disconnect(); } catch (e) { /* noop */ } }
    var ro = new ResizeObserver(function () { schedule(); });
    ro.observe(cc);
    globalThis.__m803labRO = ro;
  }
  schedule();
}
