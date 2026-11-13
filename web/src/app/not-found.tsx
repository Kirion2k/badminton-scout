import Link from "next/link";

import { Shell } from "@/components/shell";

// One message for "never existed" and "not published": it must not reveal which.
export default function NotFound() {
  return (
    <Shell>
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="num text-sm text-muted-foreground">404</p>
        <h1 className="mt-2 display text-[28px] leading-tight">Nothing here</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This page doesn’t exist, or its records aren’t published on Badminton
          Scout.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block text-primary hover:underline"
        >
          Search for a player →
        </Link>
      </div>
    </Shell>
  );
}
