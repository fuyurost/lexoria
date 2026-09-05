import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import type { UserSettings, UserSettingsPatch } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from './common';

export function useSettings() {
  return useQuery({
    queryKey: QK.settings,
    queryFn: () => api.settings.get(),
    staleTime: 60_000,
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: UserSettingsPatch) => api.settings.update(patch),
    onSuccess: (updated) => {
      qc.setQueryData<UserSettings>(QK.settings, updated);
    },
  });
}
