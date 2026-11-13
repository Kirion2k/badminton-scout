import Link from "next/link";

/** The wordmark: "mynton" set in Archivo at its narrowest, in form green. */
export function Wordmark() {
  return (
    <Link
      href="/"
      translate="no"
      className="display shrink-0 text-[25px] leading-none text-form no-underline hover:no-underline"
    >
      mynton
    </Link>
  );
}
