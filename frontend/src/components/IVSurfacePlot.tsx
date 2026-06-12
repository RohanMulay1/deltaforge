"use client";

import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { OptionQuote } from "@/types";

interface IVSurfacePlotProps {
  options: OptionQuote[];
}

interface TooltipPayload {
  payload?: { strike: number; iv: number; type: string; open_interest: number };
}

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) => {
  if (!active || !payload?.[0]?.payload) return null;
  const d = payload[0].payload;
  return (
    <div style={{ background: "rgba(16,18,22,0.95)", border: "1px solid rgba(255,255,255,0.10)", borderRadius: 12, padding: "8px 14px", fontFamily: "monospace", fontSize: 11 }}>
      <div style={{ color: "#a8acb3" }}>STRIKE: <span style={{ color: "#fff" }}>${d.strike}</span></div>
      <div style={{ color: "#a8acb3" }}>IV: <span style={{ color: d.type === "call" ? "#f5a623" : "#cf202f" }}>{d.iv.toFixed(2)}%</span></div>
      <div style={{ color: "#a8acb3" }}>OI: <span style={{ color: "#fff" }}>{d.open_interest.toLocaleString()}</span></div>
    </div>
  );
};

export default function IVSurfacePlot({ options }: IVSurfacePlotProps) {
  const maxOI = Math.max(...options.map((o) => o.open_interest), 1);

  const calls = options.filter((o) => o.type === "call").map((o) => ({
    strike: o.strike, iv: o.iv * 100, open_interest: o.open_interest, type: "call",
    size: Math.max(40, (o.open_interest / maxOI) * 400),
  }));

  const puts = options.filter((o) => o.type === "put").map((o) => ({
    strike: o.strike, iv: o.iv * 100, open_interest: o.open_interest, type: "put",
    size: Math.max(40, (o.open_interest / maxOI) * 400),
  }));

  return (
    <div className="cb-card overflow-hidden cursor-default">
      <div
        className="flex items-center justify-between px-5 py-3.5"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <span className="text-[11px] font-bold uppercase tracking-widest text-white" style={{ letterSpacing: "0.1em" }}>
          IV Surface  —  Wolfram Calibration
        </span>
        <span
          className="font-mono text-[9px] font-bold uppercase px-2.5 py-1 rounded-full"
          style={{ background: "rgba(245,166,35,0.12)", color: "#f5a623", border: "1px solid rgba(245,166,35,0.25)", letterSpacing: "0.08em" }}
        >
          SYMBOLIC
        </span>
      </div>

      <div style={{ height: 190, padding: "8px 0 0" }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 20, bottom: 20, left: 10 }}>
            <XAxis
              dataKey="strike" type="number" domain={["auto", "auto"]}
              tick={{ fill: "#7c828a", fontFamily: "monospace", fontSize: 10 }}
              tickLine={false} axisLine={{ stroke: "rgba(255,255,255,0.07)" }}
              label={{ value: "STRIKE", position: "insideBottom", offset: -12, fill: "#7c828a", fontFamily: "monospace", fontSize: 9 }}
            />
            <YAxis
              dataKey="iv" type="number" domain={[0, 30]}
              tick={{ fill: "#7c828a", fontFamily: "monospace", fontSize: 10 }}
              tickLine={false} axisLine={{ stroke: "rgba(255,255,255,0.07)" }}
              tickFormatter={(v) => `${v}%`}
            />
            <ZAxis dataKey="size" range={[40, 400]} />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(255,255,255,0.08)" }} />
            <Scatter data={calls} fill="#f5a623" fillOpacity={0.80} />
            <Scatter data={puts} fill="#cf202f" fillOpacity={0.70} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center gap-4 px-5 pb-4 pt-1">
        {[["#f5a623", "CALLS"], ["#cf202f", "PUTS"]].map(([color, label]) => (
          <span key={label} className="flex items-center gap-1.5 font-mono text-[10px]" style={{ color: "#7c828a" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
            {label}
          </span>
        ))}
        <span className="font-mono text-[10px] ml-auto" style={{ color: "#7c828a" }}>
          Surface awaiting 3D Wolfram data
        </span>
      </div>
    </div>
  );
}
