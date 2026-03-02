import { useEffect, useRef } from "react";
import { EditorView, basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";

interface Props {
  value: string;
  onChange: (val: string) => void;
}

export default function Editor({ value, onChange }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    view.current = new EditorView({
      doc: value,
      extensions: [
        basicSetup,
        markdown(),
        EditorView.updateListener.of(u => {
          if (u.docChanged) onChange(u.state.doc.toString());
        }),
      ],
      parent: ref.current,
    });
    return () => view.current?.destroy();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={ref} style={{ border: "1px solid #ccc", minHeight: 400 }} />;
}
