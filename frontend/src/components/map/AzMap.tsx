import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { AZ_VIEWBOX, project as toXY } from "./az-regions";
import { REGIONS } from "@/data/regions";

/**
 * Azerbaijan's 14 economic regions as an interactive SVG.
 *
 * Regions are shaded by a value (the money donated there in the last 30 days), on the
 * site's own ramp: near-white through the mist blue to the slate of the dark bands.
 * Projects sit on top as lime pins that pulse. Hover a region or pin for its figures,
 * click a region to zoom into it, click a pin to open its project. The wheel and a drag
 * zoom and pan; the buttons do the same for people without a wheel. Every region and
 * pin is reachable with Tab and opens with Enter.
 */

export type MapPin = {
  id: string;
  lat: number;
  lng: number;
  label: string;
  sub?: string;
  href?: string;
  /** Pins scale a little with this (e.g. money raised); any positive number. */
  weight?: number;
  done?: boolean;
};

type Props = {
  values?: Record<string, number>;
  formatValue?: (value: number) => string;
  /** Extra lines under a region's name in its tooltip. */
  detail?: (regionKey: string) => React.ReactNode;
  pins?: MapPin[];
  selected?: string | null;
  onSelect?: (regionKey: string | null) => void;
  /** Called when a pin is opened; by default the app navigates to its `href`. */
  onPin?: (pin: MapPin) => void;
  /** Draw this pin larger and ringed, e.g. on its project's page. */
  focusPinId?: string;
  /** A smaller map without controls or legend (landing teaser, project page). */
  compact?: boolean;
  zoomable?: boolean;
  /** "always" zooms on any wheel turn (the map page); "modifier" only with Ctrl or ⌘ held,
   *  so a map inside a page never hijacks its scrolling. */
  wheel?: "always" | "modifier";
  showLegend?: boolean;
  legendLabel?: string;
  ariaLabel?: string;
  className?: string;
};

const W = AZ_VIEWBOX.width;
const H = AZ_VIEWBOX.height;
const BASE = { x: 0, y: 0, w: W, h: H };
type Box = typeof BASE;

/** The ramp, low to high: the page ground, the mist blue, the dark band's slate. */
export const RAMP = ["#f5f7fb", "#c9d3e0", "#7d8798", "#35363b"];

function hex(c: string) {
  const n = parseInt(c.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rampColor(t: number) {
  const x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const f = x - i;
  const a = hex(RAMP[i]);
  const b = hex(RAMP[i + 1]);
  const m = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${m[0]}, ${m[1]}, ${m[2]})`;
}

/** Light text on the dark end of the ramp, dark text elsewhere. */
const inkOn = (t: number) => (t > 0.62 ? "#ffffff" : "#242426");

const ease = (t: number) => 1 - Math.pow(1 - t, 3);

export default function AzMap({
  values = {},
  formatValue = (v) => String(v),
  detail,
  pins = [],
  selected = null,
  onSelect,
  onPin,
  focusPinId,
  compact = false,
  zoomable = !compact,
  wheel = "modifier",
  showLegend = !compact,
  legendLabel = "Most donations",
  ariaLabel = "Map of Azerbaijan's economic regions",
  className = "",
}: Props) {
  const navigate = useNavigate();
  const wrap = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const paths = useRef<Record<string, SVGPathElement | null>>({});
  const [vb, setVb] = useState<Box>(BASE);
  const vbRef = useRef(vb);
  vbRef.current = vb;
  const tween = useRef(0);
  const drag = useRef<{ x: number; y: number; box: Box; moved: boolean } | null>(null);
  const [hover, setHover] = useState<{ kind: "region" | "pin"; key: string; x: number; y: number } | null>(null);

  // A square-root scale, so one busy region does not wash every other one out.
  const max = useMemo(() => Math.max(1, ...Object.values(values)), [values]);
  const level = useCallback((key: string) => Math.sqrt((values[key] ?? 0) / max), [values, max]);

  const animateTo = useCallback((target: Box) => {
    cancelAnimationFrame(tween.current);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const from = vbRef.current;
    if (reduce) {
      setVb(target);
      return;
    }
    const t0 = performance.now();
    const step = (now: number) => {
      const k = ease(Math.min(1, (now - t0) / 420));
      setVb({
        x: from.x + (target.x - from.x) * k,
        y: from.y + (target.y - from.y) * k,
        w: from.w + (target.w - from.w) * k,
        h: from.h + (target.h - from.h) * k,
      });
      if (k < 1) tween.current = requestAnimationFrame(step);
    };
    tween.current = requestAnimationFrame(step);
  }, []);

  useEffect(() => () => cancelAnimationFrame(tween.current), []);

  const clampBox = (b: Box): Box => {
    const w = Math.max(W / 7, Math.min(W, b.w));
    const h = (w * H) / W;
    const x = Math.max(-w * 0.25, Math.min(W - w * 0.75, b.x));
    const y = Math.max(-h * 0.25, Math.min(H - h * 0.75, b.y));
    return { x, y, w, h };
  };

  // Zoom into the selected region, or back out when it is cleared.
  useEffect(() => {
    if (!zoomable) return;
    const el = selected ? paths.current[selected] : null;
    if (!el) {
      animateTo(BASE);
      return;
    }
    const b = el.getBBox();
    const pad = 0.18;
    let w = b.width * (1 + pad * 2);
    let h = b.height * (1 + pad * 2);
    if (w / h > W / H) h = (w * H) / W;
    else w = (h * W) / H;
    w = Math.max(w, W / 3.2);
    h = (w * H) / W;
    animateTo(clampBox({ x: b.x + b.width / 2 - w / 2, y: b.y + b.height / 2 - h / 2, w, h }));
  }, [selected, zoomable, animateTo]);

  /** A point in the window to the map's own coordinates. */
  const toSvg = (clientX: number, clientY: number) => {
    const el = svg.current;
    const ctm = el?.getScreenCTM();
    if (!el || !ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  };

  const zoomBy = (factor: number, around?: { x: number; y: number }) => {
    const b = vbRef.current;
    const c = around ?? { x: b.x + b.w / 2, y: b.y + b.h / 2 };
    const w = b.w / factor;
    const h = b.h / factor;
    return clampBox({ x: c.x - (c.x - b.x) / factor, y: c.y - (c.y - b.y) / factor, w, h });
  };

  // The wheel zooms around the cursor. Registered by hand: React's onWheel is passive,
  // and the page must not scroll while the map takes the gesture.
  useEffect(() => {
    const el = svg.current;
    if (!el || !zoomable) return;
    const onWheel = (e: WheelEvent) => {
      if (wheel === "modifier" && !e.ctrlKey && !e.metaKey) return;
      if (Math.abs(e.deltaY) < 0.5) return;
      e.preventDefault();
      cancelAnimationFrame(tween.current);
      const factor = Math.exp(-e.deltaY * 0.0022);
      setVb(zoomBy(factor, toSvg(e.clientX, e.clientY)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoomable, wheel]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (!zoomable || e.button !== 0) return;
    drag.current = { x: e.clientX, y: e.clientY, box: vbRef.current, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 5) return;
    if (!d.moved) {
      d.moved = true;
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
      cancelAnimationFrame(tween.current);
      setHover(null);
    }
    const rect = svg.current!.getBoundingClientRect();
    const k = d.box.w / rect.width;
    setVb(clampBox({ ...d.box, x: d.box.x - dx * k, y: d.box.y - dy * k }));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (d?.moved) {
      (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
      // Swallow the click that ends a drag, so panning never selects a region.
      const stop = (ev: Event) => {
        ev.stopPropagation();
        window.removeEventListener("click", stop, true);
      };
      window.addEventListener("click", stop, true);
      window.setTimeout(() => window.removeEventListener("click", stop, true), 0);
    }
  };

  const tipAt = (e: React.PointerEvent | React.FocusEvent, kind: "region" | "pin", key: string) => {
    const box = wrap.current?.getBoundingClientRect();
    if (!box) return;
    if ("clientX" in e) {
      setHover({ kind, key, x: e.clientX - box.left, y: e.clientY - box.top });
    } else {
      const r = (e.target as Element).getBoundingClientRect();
      setHover({ kind, key, x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top });
    }
  };

  const openPin = (pin: MapPin) => {
    if (onPin) onPin(pin);
    else if (pin.href) navigate(pin.href);
  };

  const pick = (key: string) => onSelect?.(selected === key ? null : key);

  // Pins keep their size on screen as the map zooms.
  const k = vb.w / W;
  const maxWeight = Math.max(1, ...pins.map((p) => p.weight ?? 1));
  const pinR = (p: MapPin) => (compact ? 7 : 6 + 5 * Math.sqrt((p.weight ?? 1) / maxWeight)) * k * (p.id === focusPinId ? 1.5 : 1);

  const tipRegion = hover?.kind === "region" ? REGIONS.find((r) => r.key === hover.key) : undefined;
  const tipPin = hover?.kind === "pin" ? pins.find((p) => p.id === hover.key) : undefined;
  const labelRegion = selected ? REGIONS.find((r) => r.key === selected) : undefined;

  return (
    <div className={`v-map${compact ? " v-map--compact" : ""} ${className}`} ref={wrap}>
      <svg
        ref={svg}
        className={"v-map__svg" + (zoomable ? " is-zoomable" : "")}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        role="group"
        aria-label={ariaLabel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={() => setHover(null)}
      >
        <g className="v-map__regions">
          {REGIONS.map((r) => {
            const t = level(r.key);
            const on = selected === r.key;
            return (
              <path
                key={r.key}
                ref={(el) => (paths.current[r.key] = el)}
                d={r.d}
                className={"v-map__region" + (on ? " is-on" : "") + (selected && !on ? " is-dim" : "")}
                style={{ fill: rampColor(t) }}
                fillRule="evenodd"
                tabIndex={onSelect ? 0 : -1}
                role={onSelect ? "button" : undefined}
                aria-pressed={onSelect ? on : undefined}
                aria-label={`${r.name} (${r.nameAz}): ${formatValue(values[r.key] ?? 0)}`}
                onPointerMove={(e) => !drag.current?.moved && tipAt(e, "region", r.key)}
                onFocus={(e) => tipAt(e, "region", r.key)}
                onBlur={() => setHover(null)}
                onClick={() => onSelect && pick(r.key)}
                onKeyDown={(e) => {
                  if (onSelect && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    pick(r.key);
                  }
                }}
              />
            );
          })}
        </g>

        {labelRegion ? (
          <text
            className="v-map__label"
            x={labelRegion.cx}
            y={labelRegion.cy - 14 * k}
            style={{ fontSize: 15 * k, fill: inkOn(level(labelRegion.key)) }}
            textAnchor="middle"
          >
            {labelRegion.name}
          </text>
        ) : null}

        <g className="v-map__pins">
          {pins.map((p) => {
            const [x, y] = toXY(p.lng, p.lat);
            const r = pinR(p);
            const focus = p.id === focusPinId;
            return (
              <g
                key={p.id}
                className={"v-map__pin" + (p.done ? " is-done" : "") + (focus ? " is-focus" : "")}
                transform={`translate(${x} ${y})`}
                tabIndex={0}
                role="link"
                aria-label={`${p.label}${p.sub ? `, ${p.sub}` : ""}`}
                onPointerMove={(e) => {
                  e.stopPropagation();
                  if (!drag.current?.moved) tipAt(e, "pin", p.id);
                }}
                onFocus={(e) => tipAt(e, "pin", p.id)}
                onBlur={() => setHover(null)}
                onClick={(e) => {
                  e.stopPropagation();
                  openPin(p);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    openPin(p);
                  }
                }}
              >
                {!p.done ? <circle className="v-map__pulse" r={r} /> : null}
                <circle className="v-map__dot" r={r} style={{ strokeWidth: 2 * k }} />
              </g>
            );
          })}
        </g>
      </svg>

      {hover && (tipRegion || tipPin) ? (
        <div
          className={"v-map__tip" + (hover.x > (wrap.current?.clientWidth ?? 0) - 220 ? " is-left" : "")}
          style={{ left: hover.x, top: hover.y }}
          role="status"
        >
          {tipRegion ? (
            <>
              <b>{tipRegion.name}</b>
              <span className="v-map__tip-az">{tipRegion.nameAz}</span>
              <span className="v-map__tip-val">{formatValue(values[tipRegion.key] ?? 0)}</span>
              {detail ? <span className="v-map__tip-more">{detail(tipRegion.key)}</span> : null}
            </>
          ) : tipPin ? (
            <>
              <b>{tipPin.label}</b>
              {tipPin.sub ? <span className="v-map__tip-val">{tipPin.sub}</span> : null}
              {tipPin.href ? <span className="v-map__tip-more">Click to open the project</span> : null}
            </>
          ) : null}
        </div>
      ) : null}

      {zoomable ? (
        <div className="v-map__ctrl" role="group" aria-label="Zoom">
          <button type="button" onClick={() => animateTo(zoomBy(1.6))} aria-label="Zoom in">
            <Plus />
          </button>
          <button type="button" onClick={() => animateTo(zoomBy(1 / 1.6))} aria-label="Zoom out">
            <Minus />
          </button>
          <button
            type="button"
            onClick={() => {
              onSelect?.(null);
              animateTo(BASE);
            }}
            aria-label="Show the whole country"
          >
            <Maximize2 />
          </button>
        </div>
      ) : null}

      {showLegend ? (
        <div className="v-map__legend" aria-hidden="true">
          <span>{legendLabel}</span>
          <i style={{ background: `linear-gradient(90deg, ${RAMP.join(", ")})` }} />
        </div>
      ) : null}
    </div>
  );
}
