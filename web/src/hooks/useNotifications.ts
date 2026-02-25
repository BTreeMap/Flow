import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router';

export type Notification = {
  id: number;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
};

export function useNotifications() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const query = useQuery<Notification[]>({
    queryKey: ['notifications', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const res = await fetch(`/api/p/${projectId}/notifications`);
      if (!res.ok) throw new Error('Failed to fetch notifications');
      const data = await res.json();
      return data.notifications;
    },
    enabled: !!projectId,
  });

  const unreadCountQuery = useQuery<{ count: number }>({
    queryKey: ['notifications-unread-count', projectId],
    queryFn: async () => {
      if (!projectId) return { count: 0 };
      const res = await fetch(`/api/p/${projectId}/notifications/unread-count`);
      if (!res.ok) return { count: 0 };
      return res.json();
    },
    enabled: !!projectId,
    refetchInterval: 30000, // Poll every 30s for sync
  });

  const markReadMutation = useMutation({
    mutationFn: async (notificationId: number) => {
      if (!projectId) return;
      await fetch(`/api/p/${projectId}/notifications/${notificationId}/read`, {
        method: 'POST',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', projectId] });
      queryClient.invalidateQueries({ queryKey: ['notifications-unread-count', projectId] });
    },
  });

  return {
    notifications: query.data || [],
    isLoading: query.isLoading,
    unreadCount: unreadCountQuery.data?.count || 0,
    markRead: markReadMutation.mutate,
  };
}
