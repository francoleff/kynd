// Kynd landing page.
// - Velaris-style WebGL shader background (simplex-noise green field)
// - Small progressive enhancements (nav, reveal, signup form)

(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ============================================================
     Animated shader background (ported from the Velaris React
     component to vanilla WebGL). Green-on-dark simplex noise.
     ============================================================ */

  var VERTEX_SHADER = [
    "attribute vec2 position;",
    "varying vec2 vUv;",
    "void main() {",
    "  vUv = position * 0.5 + 0.5;",
    "  gl_Position = vec4(position, 0.0, 1.0);",
    "}",
  ].join("\n");

  var FRAGMENT_SHADER = [
    "precision highp float;",
    "varying vec2 vUv;",
    "",
    "uniform vec2  u_resolution;",
    "uniform float u_time;",
    "uniform float u_grain;",
    "uniform vec3  u_colors[4];",
    "uniform vec3  u_bg;",
    "",
    "vec3 permute(vec3 x) { return mod(((x*34.0)+1.0)*x, 289.0); }",
    "",
    "float snoise(vec2 v){",
    "  const vec4 C = vec4(0.211324865405187, 0.366025403784439,",
    "           -0.577350269189626, 0.024390243902439);",
    "  vec2 i  = floor(v + dot(v, C.yy) );",
    "  vec2 x0 = v -   i + dot(i, C.xx);",
    "  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);",
    "  vec4 x12 = x0.xyxy + C.xxzz;",
    "  x12.xy -= i1;",
    "  i = mod(i, 289.0);",
    "  vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 ))",
    "  + i.x + vec3(0.0, i1.x, 1.0 ));",
    "  vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy),",
    "    dot(x12.zw,x12.zw)), 0.0);",
    "  m = m*m ;",
    "  m = m*m ;",
    "  vec3 x = 2.0 * fract(p * C.www) - 1.0;",
    "  vec3 h = abs(x) - 0.5;",
    "  vec3 ox = floor(x + 0.5);",
    "  vec3 a0 = x - ox;",
    "  m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );",
    "  vec3 g;",
    "  g.x  = a0.x  * x0.x  + h.x  * x0.y;",
    "  g.yz = a0.yz * x12.xz + h.yz * x12.yw;",
    "  return 130.0 * dot(m, g);",
    "}",
    "",
    "void main() {",
    "  vec2 uv = vUv;",
    "  float ratio = u_resolution.x / u_resolution.y;",
    "  vec2 p = uv - 0.5;",
    "  p.x *= ratio;",
    "",
    "  float t = u_time * 0.18;",
    "",
    "  float n1 = snoise(p * 0.4 + vec2(t * 0.45, -t * 0.55));",
    "  float n2 = snoise(p * 0.55 + vec2(-t * 0.35, t * 0.45) + n1 * 0.4);",
    "  float n3 = snoise(p * 0.75 + vec2(t * 0.25, -t * 0.4) + n2 * 0.35);",
    "",
    "  vec3 col = u_bg;",
    "",
    "  float dist = length(p) * 1.5;",
    "",
    "  col = mix(col, u_colors[0], smoothstep(-0.2, 0.5, n1) * 0.22);",
    "  col = mix(col, u_colors[1], smoothstep(-0.1, 0.6, n2) * 0.18);",
    "  col = mix(col, u_colors[2], smoothstep(-0.3, 0.4, n3) * 0.35);",
    "  col = mix(col, u_colors[3], smoothstep(0.0, 0.7, n1 * n2) * 0.25);",
    "",
    "  float glow = smoothstep(0.8, 0.0, dist) * 0.1;",
    "  col += u_colors[1] * glow;",
    "",
    "  float grain = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453 + u_time);",
    "  col += (grain - 0.5) * u_grain * 0.1;",
    "",
    "  gl_FragColor = vec4(col, 1.0);",
    "}",
  ].join("\n");

  var BG = "#7db86b"; // kynd green
  var COLORS = ["#ffffff", "#ffffff", "#7db86b", "#7db86b"];
  var SPEED = 3.5;
  var GRAIN = 0.3;

  function initBackground() {
    var canvas = document.getElementById("bg-canvas");
    if (!canvas) return;

    var gl =
      canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (!gl) return; // no WebGL — the CSS fallback background shows instead

    function createShader(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    }

    var program = gl.createProgram();
    gl.attachShader(program, createShader(gl.VERTEX_SHADER, VERTEX_SHADER));
    gl.attachShader(program, createShader(gl.FRAGMENT_SHADER, FRAGMENT_SHADER));
    gl.linkProgram(program);
    gl.useProgram(program);

    var buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW
    );

    var pos = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

    var locs = {
      res: gl.getUniformLocation(program, "u_resolution"),
      time: gl.getUniformLocation(program, "u_time"),
      grain: gl.getUniformLocation(program, "u_grain"),
      colors: gl.getUniformLocation(program, "u_colors"),
      bg: gl.getUniformLocation(program, "u_bg"),
    };

    function hexToRgb(hex) {
      var h = hex.replace("#", "");
      return [
        parseInt(h.slice(0, 2), 16) / 255,
        parseInt(h.slice(2, 4), 16) / 255,
        parseInt(h.slice(4, 6), 16) / 255,
      ];
    }

    function resize() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = canvas.clientWidth * dpr;
      canvas.height = canvas.clientHeight * dpr;
      gl.viewport(0, 0, canvas.width, canvas.height);
    }

    var ro = new ResizeObserver(resize);
    ro.observe(canvas.parentElement);
    resize();

    var flat = new Float32Array(COLORS.slice(0, 4).flatMap(hexToRgb));

    function render(t) {
      gl.uniform2f(locs.res, canvas.width, canvas.height);
      gl.uniform1f(locs.time, t * 0.001 * SPEED);
      gl.uniform1f(locs.grain, GRAIN);
      gl.uniform3f(locs.bg, ...hexToRgb(BG));
      gl.uniform3fv(locs.colors, flat);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    if (reduceMotion) {
      // static first frame for reduced-motion users
      render(0);
      return;
    }

    var raf;
    function loop(t) {
      render(t);
      raf = requestAnimationFrame(loop);
    }
    raf = requestAnimationFrame(loop);
  }

  /* ============================================================
     Dock magnification (macOS style)
     Icons scale based on cursor distance — the nearest one is
     biggest, neighbours fall off smoothly. Updated every frame
     with rAF so it tracks the cursor without jank.
     ============================================================ */

  var dock = document.querySelector(".dock");
  var dockIcons = dock ? Array.prototype.slice.call(dock.querySelectorAll(".dock__icon")) : [];

  var DOCK_MAX_SCALE = 0.18; // extra scale for the hovered icon (total ~1.18x)
  var DOCK_SIGMA = 30; // falloff radius (px) — smaller = fewer neighbours affected

  function dockCenter(icon) {
    var r = icon.getBoundingClientRect();
    return r.left + r.width / 2;
  }

  function applyDockMagnify(clientX) {
    dockIcons.forEach(function (icon) {
      var dist = Math.abs(dockCenter(icon) - clientX);
      var scale = 1 + DOCK_MAX_SCALE * Math.exp(-(dist * dist) / (2 * DOCK_SIGMA * DOCK_SIGMA));
      icon.style.transform = "scale(" + scale.toFixed(4) + ")";
    });
  }

  function resetDock() {
    dockIcons.forEach(function (icon) {
      icon.style.transform = "";
    });
  }

  if (dock && dockIcons.length && !reduceMotion) {
    dock.classList.add("dock--magnify");

    var dockRaf = null;
    dock.addEventListener("mousemove", function (event) {
      if (dockRaf) return; // already scheduled this frame
      var x = event.clientX;
      dockRaf = requestAnimationFrame(function () {
        dockRaf = null;
        applyDockMagnify(x);
      });
    });

    dock.addEventListener("mouseleave", function () {
      if (dockRaf) {
        cancelAnimationFrame(dockRaf);
        dockRaf = null;
      }
      resetDock();
    });
  }

  /* ============================================================
     Reveal on scroll
     ============================================================ */

  var revealEls = document.querySelectorAll(".reveal");

  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) {
      el.classList.add("is-visible");
    });
  } else {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );

    revealEls.forEach(function (el) {
      observer.observe(el);
    });
  }

  initBackground();
})();
