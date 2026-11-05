"""Isolated Three.js renderer for the simulated 3D coaching view."""

import json

import streamlit as st


THREE_VERSION = "0.180.0"


def render_ocean_3d(configuration=None, height=620):
    """Render the 3D coaching scene without coupling it to GPS playback."""
    payload = {
        "quality": "balanced",
        "label": "SIMULATED · 3D COACHING VIEW",
        **(configuration or {}),
    }
    encoded_payload = json.dumps(payload, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    html = OCEAN_3D_HTML.replace("__OCEAN_CONFIGURATION__", encoded_payload)
    st.iframe(
        html,
        width="stretch",
        height=height,
        alt="Simulated 3D ocean coaching view with an ILCA 7 placeholder",
    )


OCEAN_3D_HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <script type="importmap">
    {{"imports":{{
      "three":"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/build/three.module.js",
      "three/addons/":"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/examples/jsm/"
    }}}}
  </script>
  <style>
    * {{ box-sizing:border-box; }}
    html,body,#scene {{ width:100%;height:100%;margin:0;overflow:hidden; }}
    body {{ background:#06151f;font-family:Inter,ui-sans-serif,system-ui,sans-serif; }}
    #scene {{ display:block; }}
    .badge {{ position:absolute;z-index:2;left:16px;top:16px;padding:8px 11px;
      border:1px solid rgba(101,213,209,.35);border-radius:999px;color:#cffffb;
      background:rgba(3,18,27,.82);font:700 10px ui-monospace,monospace;
      letter-spacing:.09em;backdrop-filter:blur(10px); }}
    .hint {{ position:absolute;z-index:2;left:16px;bottom:16px;color:#bdd2d6;
      background:rgba(3,18,27,.75);border:1px solid rgba(255,255,255,.12);
      border-radius:8px;padding:7px 10px;font:600 10px ui-monospace,monospace; }}
    .fallback {{ display:none;position:absolute;inset:0;place-items:center;padding:32px;
      text-align:center;color:#eaf8f6;background:linear-gradient(#12394c,#071c2c); }}
    .fallback strong {{ display:block;margin-bottom:8px;font-size:18px; }}
  </style>
</head>
<body>
  <canvas id="scene" aria-label="Simulated 3D ocean coaching view"></canvas>
  <div class="badge" id="badge"></div>
  <div class="hint">Drag to orbit · scroll to zoom</div>
  <div class="fallback" id="fallback"><div><strong>3D view unavailable</strong>
    <span id="fallbackReason">This browser could not start WebGL.</span></div></div>
  <script type="module">
    const configuration = __OCEAN_CONFIGURATION__;
    const canvas = document.getElementById('scene');
    const fallback = document.getElementById('fallback');
    const fallbackReason = document.getElementById('fallbackReason');
    document.getElementById('badge').textContent = configuration.label;

    function showFallback(message) {{
      canvas.style.display = 'none';
      fallbackReason.textContent = message;
      fallback.style.display = 'grid';
    }}

    const probe = document.createElement('canvas');
    if (!probe.getContext('webgl2') && !probe.getContext('webgl')) {{
      showFallback('WebGL is disabled or unsupported. Continue with the 2D GPS map.');
    }} else {{
      try {{
        const THREE = await import('three');
        const {{ OrbitControls }} = await import('three/addons/controls/OrbitControls.js');
        const renderer = new THREE.WebGLRenderer({{canvas,antialias:true,powerPreference:'high-performance'}});
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x91bfd0);
        scene.fog = new THREE.Fog(0x91bfd0, 65, 190);
        const camera = new THREE.PerspectiveCamera(46, 1, .1, 350);
        camera.position.set(18, 11, 22);

        const controls = new OrbitControls(camera, canvas);
        controls.target.set(0, 1.5, 0);
        controls.enableDamping = true;
        controls.minDistance = 8;
        controls.maxDistance = 65;
        controls.maxPolarAngle = Math.PI * .48;

        scene.add(new THREE.HemisphereLight(0xdaf5ff, 0x123546, 2.2));
        const sun = new THREE.DirectionalLight(0xfff1cf, 3.5);
        sun.position.set(-25, 35, 18);
        scene.add(sun);

        // Phase 1 uses a static water plane. GPU waves arrive in the approved ocean phase.
        const water = new THREE.Mesh(
          new THREE.PlaneGeometry(260, 260, 1, 1),
          new THREE.MeshPhysicalMaterial({{
            color:0x087f82,roughness:.18,metalness:.05,transmission:.08,
            clearcoat:1,clearcoatRoughness:.12,side:THREE.DoubleSide
          }})
        );
        water.rotation.x = -Math.PI / 2;
        scene.add(water);

        // Geometric stand-in only; Phase 3 replaces it through the GLB loader.
        const boat = new THREE.Group();
        const hull = new THREE.Mesh(
          new THREE.CapsuleGeometry(.75, 4.4, 8, 20),
          new THREE.MeshStandardMaterial({{color:0xffffff,roughness:.42}})
        );
        hull.rotation.z = Math.PI / 2;
        hull.scale.set(1, .42, .55);
        hull.position.y = .55;
        boat.add(hull);
        const mast = new THREE.Mesh(
          new THREE.CylinderGeometry(.035,.045,5.8,10),
          new THREE.MeshStandardMaterial({{color:0x263843,roughness:.5}})
        );
        mast.position.set(.25,3.2,0);
        boat.add(mast);
        const sailShape = new THREE.Shape();
        sailShape.moveTo(.25,.45);sailShape.lineTo(.25,5.85);sailShape.lineTo(-2.25,.7);sailShape.closePath();
        const sail = new THREE.Mesh(
          new THREE.ShapeGeometry(sailShape),
          new THREE.MeshStandardMaterial({{color:0xffffff,roughness:.55,side:THREE.DoubleSide,transparent:true,opacity:.9}})
        );
        sail.position.y = .3;
        boat.add(sail);
        boat.rotation.y = -.35;
        scene.add(boat);

        let visible = true;
        document.addEventListener('visibilitychange', () => {{ visible = !document.hidden; }});
        const resize = () => {{
          const width = Math.max(1, canvas.clientWidth);
          const height = Math.max(1, canvas.clientHeight);
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        }};
        new ResizeObserver(resize).observe(canvas);
        resize();

        function frame() {{
          requestAnimationFrame(frame);
          if (!visible) return;
          controls.update();
          renderer.render(scene, camera);
        }}
        frame();
      }} catch (error) {{
        console.error(error);
        showFallback('The 3D libraries could not load. Continue with the 2D GPS map.');
      }}
    }}
  </script>
</body>
</html>
"""
