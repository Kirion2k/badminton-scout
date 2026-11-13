"use client";

import { useEffect, useRef } from "react";

/** Inside a GET form: a changed select applies at once. Without JavaScript the form's own
 * submit button still does the job, so this only removes a click. */
export function AutoSubmit() {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const form = ref.current?.closest("form");
    if (!form) return;
    const submit = (e: Event) => {
      if (e.target instanceof HTMLSelectElement) form.requestSubmit();
    };
    form.addEventListener("change", submit);
    return () => form.removeEventListener("change", submit);
  }, []);
  return <span ref={ref} hidden />;
}
