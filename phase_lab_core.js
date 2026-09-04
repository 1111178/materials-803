/* phase_lab_core.js —— 相图实验室纯判相/杠杆/Fe-C 公式(无 DOM)。
 * 逐行对齐 app/phase_lab.py 的 classify / fec_room_readout,spec 由 system_spec() 导出。
 * 既可在浏览器(iframe 组件内)用,也可在 node 下 require 做锚点对照。
 */
(function (global) {
  'use strict';

  function clamp01(w) { return w < 0 ? 0 : (w > 1 ? 1 : w); }

  // 折线 [[x,T],...](T 升序),在温度 T 线性插值 x
  function interpXAtT(arc, T) {
    if (T <= arc[0][1]) return arc[0][0];
    var last = arc[arc.length - 1];
    if (T >= last[1]) return last[0];
    var lo = 0, hi = arc.length - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (arc[mid][1] <= T) lo = mid; else hi = mid; }
    var x0 = arc[lo][0], t0 = arc[lo][1], x1 = arc[hi][0], t1 = arc[hi][1];
    if (t1 - t0 === 0) return x0;
    return x0 + (x1 - x0) * (T - t0) / (t1 - t0);
  }

  // even-odd 射线法
  function ptInPoly(x, T, poly) {
    var inside = false, n = poly.length;
    for (var i = 0; i < n; i++) {
      var p1 = poly[i], p2 = poly[(i + 1) % n];
      var x1 = p1[0], y1 = p1[1], x2 = p2[0], y2 = p2[1];
      if ((y1 > T) !== (y2 > T)) {
        var xin = x1 + (T - y1) * (x2 - x1) / (y2 - y1);
        if (x < xin) inside = !inside;
      }
    }
    return inside;
  }

  function centroid(poly) {
    var x = 0, y = 0, n = poly.length;
    for (var i = 0; i < n; i++) { x += poly[i][0]; y += poly[i][1]; }
    return [x / n, y / n];
  }

  function pureOrLine(spec, x, T) {
    if (spec.fec) {
      if (x >= 6.69 - 0.012) {
        return T <= 1227 ? ['Fe₃C', 'Fe₃C 渗碳体(6.69%C,≤1227℃ 稳定)']
                         : ['L', 'Fe₃C 熔化后的液相(>1227℃,示意)'];
      }
      if (x <= 1e-9) {
        if (T >= 1538) return ['L', '纯铁熔点以上 → 液相 L'];
        if (T >= 1394) return ['δ', '纯铁 δ 相(1394–1538℃)'];
        if (T >= 912) return ['γ', '纯铁 γ 相(奥氏体,912–1394℃)'];
        return ['α', '纯铁 α 相(铁素体,<912℃)'];
      }
      return [null, null];
    }
    var x0 = spec.x_domain[0], x1 = spec.x_domain[1];
    if (x <= x0 + 1e-9) return [spec.endA || 'α', (spec.compA ? '纯 ' + spec.compA + '(端点组元)固相' : '左端组元固相')];
    if (x >= x1 - 1e-9) return [spec.endB || 'β', (spec.compB ? '纯 ' + spec.compB + '(端点组元)固相' : '右端组元固相')];
    return [null, null];
  }

  function classify(spec, x, T) {
    var out = { kind: '', region: '', phases: [], text: '', x: x, T: T };
    var sp = pureOrLine(spec, x, T);
    if (sp[0] !== null) {
      out.kind = 'single'; out.region = sp[0]; out.phases = [sp[0]]; out.text = sp[1] || sp[0];
      return out;
    }
    for (var i = 0; i < spec.invariants.length; i++) {
      var inv = spec.invariants[i];
      if (Math.abs(T - inv.T) <= 2 && (inv.x_lo - 0.02) <= x && x <= (inv.x_hi + 0.02)) {
        out.kind = 'invariant'; out.text = inv.txt;
        return out;
      }
    }
    var best = null;
    for (var j = 0; j < spec.regions.length; j++) {
      var r = spec.regions[j];
      if (!ptInPoly(x, T, r.poly)) continue;
      if (r.kind === 'single') {
        out.kind = 'single'; out.region = r.name; out.phases = r.phases; out.text = r.name;
        return out;
      }
      var x1 = interpXAtT(spec.arcs[r.left], T);
      var x2 = interpXAtT(spec.arcs[r.right], T);
      if (x1 < x2 && (x1 - 0.02) <= x && x <= (x2 + 0.02)) {
        var w = (x2 - x1 > 1e-9) ? (x - x1) / (x2 - x1) : 0;
        var wr = clamp01(w);
        out.kind = 'two'; out.region = r.name; out.phases = r.phases;
        out.left = x1; out.right = x2; out.w_right = wr; out.w_left = 1 - wr;
        return out;
      }
      best = r;
    }
    if (best) {
      out.kind = 'single'; out.region = best.name; out.phases = best.phases;
      out.text = best.name + '（边）';
    }
    return out;
  }

  function pct(w) { w = w < 0 ? 0 : (w > 1 ? 1 : w); return w * 100; }

  // Fe-C 室温组织/相组成(考点公式),c: wt%C。返回 {cls, org:[{name,frac,col}], ph:[...], tags}
  function fecRoomReadout(c, spec) {
    var C = (spec && spec.colors) || { 'α': '#F5B85A', 'Fe₃C': '#F27D8F' };
    var A = C['α'] || '#F5B85A', F = C['Fe₃C'] || '#F27D8F';
    var out = { cls: '', org: [], ph: [], tags: '' };
    function add(list, name, frac, col) { list.push({ name: name, frac: pct(frac), col: col }); }
    if (c < 0.0218) {
      out.cls = '工业纯铁(α 铁素体)';
      add(out.org, '铁素体 F', 1.0, A);
      out.tags = '组织:铁素体 F(+极微量三次渗碳体 Fe₃CⅢ);属钢?不,为纯铁。';
    } else if (Math.abs(c - 0.77) < 0.005) {
      out.cls = '共析钢(珠光体钢)';
      add(out.org, '珠光体 P', 1.0, F);
      out.tags = '含碳 0.77%(S 点):全部为珠光体 P(铁素体+渗碳体层片机械混合物)。';
    } else if (c < 0.77) {
      var wP = (c - 0.0218) / (0.77 - 0.0218);
      out.cls = '亚共析钢';
      add(out.org, '铁素体 F', 1 - wP, A);
      add(out.org, '珠光体 P', wP, F);
      out.tags = '组织:F + P;先共析铁素体从 γ(A3 以下)析出,727℃ 剩余 γ 转 P。';
    } else if (c < 2.11) {
      var wP2 = (6.69 - c) / (6.69 - 0.77);
      out.cls = '过共析钢';
      add(out.org, '珠光体 P', wP2, F);
      add(out.org, '二次渗碳体 Fe₃CⅡ', 1 - wP2, F);
      out.tags = '组织:P + 网状二次渗碳体 Fe₃CⅡ(由 γ 沿 Acm 析出,晶界网状)。';
    } else if (Math.abs(c - 4.30) < 0.005) {
      out.cls = '共晶白口铁';
      add(out.org, '变态莱氏体 Ld′', 1.0, F);
      out.tags = '含碳 4.3%(C 点):全部为变态莱氏体 Ld′。';
    } else if (c < 4.30) {
      var wLd = (c - 2.11) / (4.30 - 2.11);
      var wg = 1 - wLd;
      var wFeC2 = wg * (2.11 - 0.77) / (6.69 - 0.77);
      var wP3 = wg - wFeC2;
      out.cls = '亚共晶白口铁';
      add(out.org, '珠光体 P', wP3, A);
      add(out.org, '二次渗碳体 Fe₃CⅡ', wFeC2, F);
      add(out.org, '变态莱氏体 Ld′', wLd, F);
      out.tags = '组织:Ld′ + P + Fe₃CⅡ(先共晶 γ 冷却中二次 Fe₃CⅡ 沿晶界析出,余转 P)。二次渗碳体份额为组合推导(教学)。';
    } else if (c <= 6.69) {
      var wLd2 = (6.69 - c) / (6.69 - 4.30);
      out.cls = '过共晶白口铁';
      add(out.org, '一次渗碳体 Fe₃CⅠ', 1 - wLd2, F);
      add(out.org, '变态莱氏体 Ld′', wLd2, F);
      out.tags = '组织:Fe₃CⅠ(粗条状,自液相析出)+ Ld′。';
    }
    var wC = c >= 0.0008 ? (c - 0.0008) / (6.69 - 0.0008) : 0.0;
    add(out.ph, '铁素体 α', 1 - wC, A);
    add(out.ph, '渗碳体 Fe₃C', wC, F);
    return out;
  }

  var API = {
    interpXAtT: interpXAtT,
    ptInPoly: ptInPoly,
    centroid: centroid,
    classify: classify,
    fecRoomReadout: fecRoomReadout,
    clamp01: clamp01
  };
  if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
  else { global.LabCore = API; }
})(typeof globalThis !== 'undefined' ? globalThis : this);
