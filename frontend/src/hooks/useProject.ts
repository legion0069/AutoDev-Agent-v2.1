import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";

export const useDashboard = () =>
  useQuery({ queryKey: ["dashboard"], queryFn: apiService.dashboard, refetchInterval: 5000 });

export const useProjectStatus = () =>
  useQuery({ queryKey: ["project-status"], queryFn: apiService.status, refetchInterval: 3000 });

export const useRoadmap = () =>
  useQuery({ queryKey: ["roadmap"], queryFn: apiService.roadmap, retry: 1 });

export const useProjectHistory = () =>
  useQuery({ queryKey: ["history"], queryFn: apiService.history, retry: 1 });

export const useApiHealth = () =>
  useQuery({ queryKey: ["api-health"], queryFn: apiService.health, refetchInterval: 10_000, retry: 1 });
