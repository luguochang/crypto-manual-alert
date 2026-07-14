import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <section className="route-state">
      <p className="section-kicker">404</p>
      <h1>没有找到这个页面</h1>
      <p>返回当前可用的分析工作台。</p>
      <Link href="/work">
        <ArrowLeft size={18} aria-hidden="true" />
        返回 Work
      </Link>
    </section>
  );
}
