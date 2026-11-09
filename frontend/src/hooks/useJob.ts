import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState as useStateCompat } from "react";
import { api } from "../api/client";
import { isActive, type Job } from "../api/types";

/** Poll a job until it finishes; runs `onDone` once when it reaches `done`. */
export function useJob(jobId: number | null | undefined, onDone?: (job: Job) => void, invalidate: unknown[][] = []) {
  const qc = useQueryClient();
  const fired = useRef<number | null>(null);
  const q = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId as number),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "done" || s === "failed" || s === "cancelled" ? false : s === "waiting" ? 2000 : 800;
    },
  });
  useEffect(() => {
    const j = q.data;
    if (!j || fired.current === j.id) return;
    if (j.status === "done" || j.status === "failed" || j.status === "cancelled") {
      fired.current = j.id;
      invalidate.forEach((key) => qc.invalidateQueries({ queryKey: key }));
      if (j.status === "done") onDone?.(j);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data]);
  // "waiting" (for the user in ChatGPT) still counts as running: polling continues.
  const running = !!q.data && isActive(q.data.status);
  return { job: q.data, running: running || (!!jobId && !q.data) };
}

/** Remember the job a step started; on reload pick up a still-running one. */
export function useStepJob(bookId: number, types: string[]) {
  const [jobId, setJobId] = useStateCompat<number | null>(null);
  const active = useQuery({
    queryKey: ["jobs", bookId, types.join(",")],
    queryFn: () => api.jobs(bookId),
    enabled: jobId === null,
    staleTime: 0,
  });
  useEffect(() => {
    if (jobId !== null || !active.data) return;
    const running = active.data.find((j) => types.includes(j.type) && isActive(j.status));
    if (running) setJobId(running.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active.data]);
  return [jobId, setJobId] as const;
}
