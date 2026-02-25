import { useEffect } from 'react';
import { useNotifications } from '../hooks/useNotifications';
import { Card, CardHeader, CardContent } from '../components/Card';
import { useNavigate, useParams } from 'react-router';
import { ArrowLeft } from 'lucide-react';

export function UpdatesPage() {
  const { notifications, isLoading, markRead } = useNotifications();
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();

  // Mark all unread as read when they appear
  useEffect(() => {
    notifications.forEach((n) => {
      if (!n.read_at) {
        markRead(n.id);
      }
    });
  }, [notifications, markRead]);

  return (
    <div className="flex flex-col h-full space-y-4">
      <div className="flex items-center gap-2">
         <button onClick={() => navigate(-1)} className="p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/10">
            <ArrowLeft className="w-5 h-5" />
         </button>
         <h1 className="text-2xl font-bold">Updates</h1>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {isLoading && <p className="text-center p-4">Loading...</p>}
        {!isLoading && notifications.length === 0 && (
          <p className="text-gray-500 text-center mt-10">No updates yet.</p>
        )}
        {notifications.map((n) => (
          <Card
            key={n.id}
            className={`cursor-pointer hover:bg-surface-2 transition-colors ${!n.read_at ? "border-primary border-2" : ""}`}
            onClick={() => {
                // If the notification has a payload with server_msg_id, we could link to it?
                // For now, we just link to the chat thread as requested.
                // Assuming "jumps to the chat to the exact message" implies going to chat.
                // We don't have deep linking scroll yet, but this is the primary interaction.
                navigate(`/p/${projectId}/chat`);
            }}
          >
            <CardHeader className="pb-2">
              <div className="flex justify-between items-start">
                <h3 className="font-semibold text-lg">{n.title}</h3>
                <span className="text-xs text-text-muted">
                  {new Date(n.created_at).toLocaleDateString()} {new Date(n.created_at).toLocaleTimeString()}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap">{n.body}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
