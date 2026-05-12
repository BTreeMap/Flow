import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { UpdatesPage } from './UpdatesPage';
import * as useNotificationsHook from '../hooks/useNotifications';
import * as router from 'react-router';

// Mock react-router
vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router');
  return {
    ...actual,
    useNavigate: vi.fn(),
    useParams: vi.fn(),
  };
});

describe('UpdatesPage', () => {
  const mockMarkRead = vi.fn();
  const mockNavigate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(router, 'useNavigate').mockReturnValue(mockNavigate);
    vi.spyOn(router, 'useParams').mockReturnValue({ projectId: 'test-project' });
  });

  it('renders loading state', () => {
    vi.spyOn(useNotificationsHook, 'useNotifications').mockReturnValue({
      notifications: [],
      isLoading: true,
      unreadCount: 0,
      markRead: mockMarkRead,
    });

    render(<UpdatesPage />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders empty state', () => {
    vi.spyOn(useNotificationsHook, 'useNotifications').mockReturnValue({
      notifications: [],
      isLoading: false,
      unreadCount: 0,
      markRead: mockMarkRead,
    });

    render(<UpdatesPage />);
    expect(screen.getByText('No updates yet.')).toBeInTheDocument();
  });

  it('renders notifications and marks unread as read on mount', () => {
    const notifications = [
      { id: 1, title: 'Nudge 1', body: 'Body 1', created_at: new Date().toISOString(), read_at: null, membership_id: 1, payload_json: '{}', project_display_name: 'Test', project_id: 'test-project' }, // Unread
      { id: 2, title: 'Nudge 2', body: 'Body 2', created_at: new Date().toISOString(), read_at: '2023-01-01', membership_id: 1, payload_json: '{}', project_display_name: 'Test', project_id: 'test-project' }, // Read
    ];

    vi.spyOn(useNotificationsHook, 'useNotifications').mockReturnValue({
      notifications,
      isLoading: false,
      unreadCount: 1,
      markRead: mockMarkRead,
    });

    render(<UpdatesPage />);

    expect(screen.getByText('Nudge 1')).toBeInTheDocument();
    expect(screen.getByText('Body 1')).toBeInTheDocument();
    expect(screen.getByText('Nudge 2')).toBeInTheDocument();

    // Should mark notification 1 as read
    expect(mockMarkRead).toHaveBeenCalledWith(1);
    // Should NOT mark notification 2 as read (already read)
    expect(mockMarkRead).not.toHaveBeenCalledWith(2);
  });

  it('navigates to chat on card click', () => {
    const notifications = [
        { id: 1, title: 'Nudge 1', body: 'Body 1', created_at: new Date().toISOString(), read_at: null, membership_id: 1, payload_json: '{}', project_display_name: 'Test', project_id: 'test-project' },
    ];

    vi.spyOn(useNotificationsHook, 'useNotifications').mockReturnValue({
      notifications,
      isLoading: false,
      unreadCount: 1,
      markRead: mockMarkRead,
    });

    render(<UpdatesPage />);

    const card = screen.getByText('Nudge 1').closest('div');
    if (!card) throw new Error('Card not found');
    fireEvent.click(card); // Click the card

    expect(mockNavigate).toHaveBeenCalledWith('/p/test-project/chat');
  });

  it('back button navigates back', () => {
     vi.spyOn(useNotificationsHook, 'useNotifications').mockReturnValue({
      notifications: [],
      isLoading: false,
      unreadCount: 0,
      markRead: mockMarkRead,
    });

    render(<UpdatesPage />);

    // Find back button (button with ArrowLeft icon, likely first button)
    const buttons = screen.getAllByRole('button');
    const backButton = buttons[0];
    if (!backButton) throw new Error('Back button not found');

    fireEvent.click(backButton);
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });
});
