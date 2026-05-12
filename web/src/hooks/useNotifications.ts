import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';
import type { UnifiedNotificationItem } from '../api/types';

export type Notification = UnifiedNotificationItem;

export function useNotifications(projectId?: string) {
  const queryClient = useQueryClient();

  const query = useQuery<UnifiedNotificationItem[]>({
    queryKey: ['notifications', projectId ?? 'all'],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (projectId) params.project_id = projectId;
      const { data, error } = await api.GET('/notifications', {
        params: { query: params },
      });
      if (error) throw new Error('Failed to fetch notifications');
      return data.notifications;
    },
  });

  const unreadCountQuery = useQuery<{ count: number }>({
    queryKey: ['notifications-unread-count', projectId ?? 'all'],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (projectId) params.project_id = projectId;
      const { data, error } = await api.GET('/notifications/unread-count', {
        params: { query: params },
      });
      if (error) return { count: 0 };
      return { count: data.count };
    },
    refetchInterval: 30000,
  });

  const markReadMutation = useMutation({
    mutationFn: async (notificationId: number) => {
      await api.POST('/notifications/{notification_id}/read', {
        params: { path: { notification_id: notificationId } },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] });
    },
  });

  return {
    notifications: query.data || [],
    isLoading: query.isLoading,
    unreadCount: unreadCountQuery.data?.count || 0,
    markRead: markReadMutation.mutate,
  };
}
