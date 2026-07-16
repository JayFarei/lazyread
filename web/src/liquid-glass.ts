// Realistic liquid-glass refraction for `.liquid` surfaces.
//
// Technique: an SVG displacement filter is applied to the backdrop with
// `backdrop-filter: url(#lg-dist)`, so live page content bends around the
// glass edges while the interior stays legible. The displacement map is a
// rounded-rectangle signed-distance field rendered to a canvas: neutral
// (128, 128) in the middle, pushing outward toward the rim, which is how the
// open-source liquid glass implementations (shuding/liquid-glass,
// deepika-builds/liquid-glass, nikdelvin/liquid-glass) model Apple's effect.
// Only Chromium applies SVG filters to backdrops; other engines keep the
// layered glassmorphism fallback declared in CSS.

const MAP_SIZE = 160;

function displacementMap(): string {
  const canvas = document.createElement("canvas");
  canvas.width = MAP_SIZE;
  canvas.height = MAP_SIZE;
  const context = canvas.getContext("2d");
  if (!context) return "";
  const image = context.createImageData(MAP_SIZE, MAP_SIZE);
  const half = MAP_SIZE / 2;
  const radius = MAP_SIZE * 0.34;
  const rim = radius * 1.1;
  for (let y = 0; y < MAP_SIZE; y += 1) {
    for (let x = 0; x < MAP_SIZE; x += 1) {
      const px = x - half + 0.5;
      const py = y - half + 0.5;
      const dx = Math.abs(px) - (half - radius);
      const dy = Math.abs(py) - (half - radius);
      const outside = Math.hypot(Math.max(dx, 0), Math.max(dy, 0));
      const distance = outside + Math.min(Math.max(dx, dy), 0);
      const edge = Math.min(Math.max((distance - radius + rim) / rim, 0), 1);
      const strength = edge * edge * edge;
      const length = Math.hypot(px, py) || 1;
      const offset = (y * MAP_SIZE + x) * 4;
      image.data[offset] = Math.round(128 + (px / length) * strength * 110);
      image.data[offset + 1] = Math.round(128 + (py / length) * strength * 110);
      image.data[offset + 2] = 128;
      image.data[offset + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  return canvas.toDataURL();
}

export function initLiquidGlass(document_: Document = document): void {
  if (document_.getElementById("lg-filters")) return;
  const chromium = /Chrom(e|ium)\//.test(navigator.userAgent);
  const supported = typeof CSS !== "undefined" && CSS.supports?.("backdrop-filter", "url(#lg-dist)");
  if (!chromium || !supported) return;
  const map = displacementMap();
  if (!map) return;
  const host = document_.createElement("div");
  host.id = "lg-filters";
  host.setAttribute("aria-hidden", "true");
  host.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
  host.innerHTML = `<svg width="0" height="0">
    <filter id="lg-dist" x="-8%" y="-8%" width="116%" height="116%" color-interpolation-filters="sRGB">
      <feImage href="${map}" preserveAspectRatio="none" result="map"/>
      <feDisplacementMap in="SourceGraphic" in2="map" scale="34" xChannelSelector="R" yChannelSelector="G"/>
    </filter>
  </svg>`;
  document_.body.append(host);
  document_.documentElement.classList.add("lg-refract");
}
