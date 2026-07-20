import Image from "next/image";
import Link from "next/link";

export function BrandLockup() {
  return (
    <Link className="brand-lockup" href="/home" prefetch={false} aria-label="Signal Desk 首页">
      <span className="brand-mark" aria-hidden="true">
        <Image src="/signal-desk-mark.svg" width={30} height={30} alt="" priority />
      </span>
      <span className="brand-copy">
        <strong>SIGNAL DESK</strong>
        <span>Intelligence workspace</span>
      </span>
    </Link>
  );
}
