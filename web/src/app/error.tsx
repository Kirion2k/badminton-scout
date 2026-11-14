"use client";

import { Button } from "@/components/ui/button";

// Never shows the underlying error: it may carry internal detail. The digest lets logs match it.
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main id="main" className="mx-auto max-w-md flex-1 px-4 py-24 text-center">
      <h1 className="display text-[28px] leading-tight">
        The data service didn’t answer
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Mynton couldn’t load these records just now. Nothing on your
        side caused this.
      </p>
      <Button className="mt-6" onClick={reset}>
        Try again
      </Button>
      {error.digest && (
        <p className="num mt-4 text-xs text-muted-foreground">
          Reference {error.digest}
        </p>
      )}
    </main>
  );
}
