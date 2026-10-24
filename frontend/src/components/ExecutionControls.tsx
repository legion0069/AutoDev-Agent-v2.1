import { LoaderCircle, Pause, Play, Square } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiService, errorMessage } from "../services/api";
import { useNotifications } from "./Notifications";
import type { ProjectSummary } from "../types";

export function ExecutionControls({ project }: { project?: ProjectSummary }) {
  const queryClient = useQueryClient();
  const { notify } = useNotifications();
  const action = useMutation({
    mutationFn: (name: "start" | "pause" | "resume" | "stop") =>
      apiService.action(name, project?.project_id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project-status"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["history"] }),
        queryClient.invalidateQueries({ queryKey: ["roadmap"] }),
      ]);
      notify("Execution control updated.");
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const running = project?.status === "running";
  const canResume = ["planned", "paused", "stopped", "waiting"].includes(project?.status ?? "");

  return (
    <div className="flex flex-wrap gap-2">
      {running ? (
        <button disabled={action.isPending} onClick={() => action.mutate("pause")} className="button-secondary"><Pause className="size-4" />Pause</button>
      ) : (
        <button disabled={action.isPending || !canResume} onClick={() => action.mutate(project?.status === "planned" ? "start" : "resume")} className="button-primary">
          {action.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Play className="size-4" />}{project?.status === "planned" ? "Run project" : "Resume"}
        </button>
      )}
      <button disabled={action.isPending || !project || ["completed", "stopped"].includes(project.status)} onClick={() => action.mutate("stop")} className="button-secondary text-rose-300 hover:border-rose-400/30 hover:text-rose-200"><Square className="size-4" />Stop</button>
    </div>
  );
}
