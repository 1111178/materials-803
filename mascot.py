# -*- coding: utf-8 -*-
"""互动吉祥物组件：圆形角色 + 眼睛跟随鼠标 + 呼吸动画。

用法（在 Streamlit 里一行嵌入）：
    import streamlit.components.v1 as components
    from mascot import mascot_html

    components.html(mascot_html(size=200, color="cream"), height=224, width=224)

参数：
    size  : 角色直径（像素），默认 200
    color : "green"（浅绿）或 "cream"（奶黄）

说明：
    - 背景透明，不遮挡内容；移动端自动缩小（超小屏直接隐藏）。
    - 因为 Streamlit 用 iframe 渲染组件，眼珠跟随只在鼠标位于该组件区域时生效
      （这是 iframe 的固有隔离，页面级全屏跟随需要浮层方案，见 readme 备注）。
"""

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  html, body { margin:0; padding:0; background:transparent; overflow:hidden; }
  .stage { width:100%; height:100%; display:flex; align-items:center; justify-content:center; }
  .scale { position:relative; width:__SIZE__px; height:__SIZE__px; }
  .backdrop { position:absolute; inset:-10px; border-radius:50%; background:__BACKDROP__; }
  .mascot {
    position:relative; width:100%; height:100%;
    border-radius:50%;
    background:__BODY__;
    border:__BORDER__px solid #3F4A5A;
    box-shadow: inset 0 -10px 18px rgba(0,0,0,0.06), 0 6px 16px rgba(0,0,0,0.08);
    animation:breathe 3.2s ease-in-out infinite;
  }
  @keyframes breathe {
    0%, 100% { transform:translateY(0); }
    50%      { transform:translateY(-5px); }
  }
  .eye {
    position:absolute; top:31%; width:27%; height:27%;
    background:#fff; border-radius:50%; border:2px solid #3F4A5A;
  }
  .eye.left  { left:15%; }
  .eye.right { right:15%; }
  .pupil {
    position:absolute; left:50%; top:50%; width:46%; height:46%;
    background:#2B2B33; border-radius:50%;
    transform:translate(-50%,-50%); transition:transform 0.08s ease-out;
  }
  @media (max-width:640px) { .scale { transform:scale(0.65); } }
  @media (max-width:400px) { .scale { display:none; } }
</style>
</head>
<body>
<div class="stage">
  <div class="scale">
    <div class="backdrop"></div>
    <div class="mascot" id="mascot">
      <div class="eye left"><div class="pupil"></div></div>
      <div class="eye right"><div class="pupil"></div></div>
    </div>
  </div>
</div>
<script>
(function(){
  var eyes = document.querySelectorAll('.eye');
  var pupils = document.querySelectorAll('.pupil');
  function move(x, y){
    for (var i = 0; i < eyes.length; i++){
      var r = eyes[i].getBoundingClientRect();
      var ex = r.left + r.width / 2, ey = r.top + r.height / 2;
      var dx = x - ex, dy = y - ey;
      var d = Math.sqrt(dx * dx + dy * dy) || 1;
      var k = Math.min(d, r.width * 0.24) / d;   // 限制眼珠不跑出眼眶
      pupils[i].style.transform =
        'translate(calc(-50% + ' + (dx * k).toFixed(1) + 'px), calc(-50% + ' + (dy * k).toFixed(1) + 'px))';
    }
  }
  function reset(){
    for (var i = 0; i < pupils.length; i++){
      pupils[i].style.transform = 'translate(-50%,-50%)';
    }
  }
  document.addEventListener('mousemove', function(e){ move(e.clientX, e.clientY); });
  document.addEventListener('touchmove', function(e){
    if (e.touches.length) move(e.touches[0].clientX, e.touches[0].clientY);
  }, {passive:true});
  document.addEventListener('mouseleave', reset);
  document.addEventListener('touchend', reset);
})();
</script>
</body>
</html>"""


COLORS = {
    "green": "#C6ECC0",   # 浅绿
    "cream": "#FFF1C1",   # 奶黄
}


def mascot_html(size=200, color="green", backdrop=None):
    """返回互动吉祥物的完整 HTML 字符串，可直接交给 components.html。"""
    body = COLORS.get(color, COLORS["green"])
    border = max(3, int(round(size * 0.025)))
    bg = backdrop or "transparent"
    return (
        _TEMPLATE
        .replace("__SIZE__", str(int(size)))
        .replace("__BORDER__", str(border))
        .replace("__BODY__", body)
        .replace("__BACKDROP__", bg)
    )
