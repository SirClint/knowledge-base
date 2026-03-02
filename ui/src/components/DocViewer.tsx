import { marked } from "marked";

interface Props { body: string; title: string; }

export default function DocViewer({ body, title }: Props) {
  return (
    <div>
      <h1>{title}</h1>
      <div dangerouslySetInnerHTML={{ __html: marked(body) as string }} />
    </div>
  );
}
