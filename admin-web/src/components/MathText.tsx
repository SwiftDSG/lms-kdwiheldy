"use client";

import katex from "katex";
import "katex/dist/katex.min.css";

type Segment =
  | { type: "text"; content: string }
  | { type: "math"; content: string; display: boolean };

function parse(text: string): Segment[] {
  const segments: Segment[] = [];

  // Split on $$...$$ first (display math)
  const displayParts = text.split(/(\$\$[\s\S]+?\$\$)/);

  for (const part of displayParts) {
    if (part.startsWith("$$") && part.endsWith("$$") && part.length > 4) {
      segments.push({ type: "math", content: part.slice(2, -2), display: true });
    } else {
      // Split remaining text on $...$ (inline math)
      const inlineParts = part.split(/(\$[^$\n]+?\$)/);
      for (const ip of inlineParts) {
        if (ip.startsWith("$") && ip.endsWith("$") && ip.length > 2) {
          segments.push({ type: "math", content: ip.slice(1, -1), display: false });
        } else if (ip) {
          segments.push({ type: "text", content: ip });
        }
      }
    }
  }

  return segments;
}

interface Props {
  text: string;
  className?: string;
}

export default function MathText({ text, className }: Props) {
  const segments = parse(text);

  return (
    <span className={className}>
      {segments.map((seg, i) =>
        seg.type === "text" ? (
          <span key={i} style={{ whiteSpace: "pre-wrap" }}>
            {seg.content}
          </span>
        ) : (
          <span
            key={i}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(seg.content, {
                displayMode: seg.display,
                throwOnError: false,
                output: "html",
              }),
            }}
          />
        )
      )}
    </span>
  );
}
