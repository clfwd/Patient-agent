import type { ReactNode } from "react";

function inline(content: string): ReactNode[] {
  const parts = content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index} className="rounded bg-black/[0.045] px-1.5 py-0.5 font-mono text-[0.9em] text-foreground">{part.slice(1, -1)}</code>;
    return part;
  });
}

function isTableDivider(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

export function MarkdownAnswer({ content }: { content: string }) {
  const lines = content.split("\n");
  const output: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.startsWith("```")) {
      const language = line.slice(3).trim(); const code: string[] = []; index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) { code.push(lines[index]); index += 1; }
      output.push(<pre key={`code-${index}`} className="my-4 overflow-x-auto rounded-lg bg-[#f5f5f5] px-4 py-3 text-[13px] leading-6 text-foreground">{language ? <span className="mb-2 block text-xs text-muted">{language}</span> : null}<code>{code.join("\n")}</code></pre>);
      index += 1; continue;
    }
    if (line.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const rows = [line]; index += 2;
      while (index < lines.length && lines[index].includes("|")) { rows.push(lines[index]); index += 1; }
      const cells = (row: string) => row.replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
      output.push(<div key={`table-${index}`} className="my-4 overflow-x-auto border-y border-line"><table className="w-full border-collapse text-left text-sm"><thead className="bg-black/[0.025] text-foreground"><tr>{cells(rows[0]).map((cell, cellIndex) => <th key={cellIndex} className="whitespace-nowrap px-3 py-2.5 font-medium">{inline(cell)}</th>)}</tr></thead><tbody>{rows.slice(1).map((row, rowIndex) => <tr key={rowIndex} className="border-t border-line">{cells(row).map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-2.5 text-muted">{inline(cell)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      const Tag = heading[1].length === 1 ? "h2" : heading[1].length === 2 ? "h3" : "h4";
      output.push(<Tag key={`heading-${index}`} className="mb-2 mt-7 font-semibold tracking-tight text-foreground">{inline(heading[2])}</Tag>);
      index += 1; continue;
    }
    const listMatch = /^(\s*)([-*+] |\d+\. )(.+)$/.exec(line);
    if (listMatch) {
      const ordered = /\d+\. /.test(listMatch[2]); const items: string[] = [];
      while (index < lines.length) { const item = /^(\s*)([-*+] |\d+\. )(.+)$/.exec(lines[index]); if (!item || /\d+\. /.test(item[2]) !== ordered) break; items.push(item[3]); index += 1; }
      const List = ordered ? "ol" : "ul";
      output.push(<List key={`list-${index}`} className={`my-3 space-y-1.5 pl-5 ${ordered ? "list-decimal" : "list-disc"}`}>{items.map((item, itemIndex) => <li key={itemIndex} className="pl-1">{inline(item)}</li>)}</List>);
      continue;
    }
    if (!line.trim()) { index += 1; continue; }
    const paragraph: string[] = [line]; index += 1;
    while (index < lines.length && lines[index].trim() && !lines[index].startsWith("```") && !/^(#{1,3})\s+/.test(lines[index]) && !/^(\s*)([-*+] |\d+\. )/.test(lines[index])) { if (lines[index].includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) break; paragraph.push(lines[index]); index += 1; }
    output.push(<p key={`paragraph-${index}`} className="my-3 first:mt-0">{inline(paragraph.join(" "))}</p>);
  }
  return <div className="markdown-answer text-[15px] leading-7 text-foreground sm:text-base sm:leading-8">{output}</div>;
}
