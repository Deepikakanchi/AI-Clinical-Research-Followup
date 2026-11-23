/*
 * pages/coordinator/DashboardPage.jsx - Coordinator dashboard.
 * Uses Person 2's endpoints: GET /api/reports/follow-ups (counts calculated in SQL,
 * limited to the logged-in coordinator's participants) and GET /api/visits.  US-28, US-29.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarDays, CalendarX2, Check, ChevronRight, CircleAlert, Clock3, FileClock, UsersRound } from 'lucide-react';
import { api } from '@/api/client';
import { useAuth } from '@/components/common/AuthContext';
import { Badge, DataTable, LoadState, PageHeading, StudySelect, dateTime, pretty, useApi } from '@/components/common/ui';

const CARDS = [
  ['active_participants', 'Active participants', UsersRound, 'success', 'Consented and enrolled'],
  ['due_7_days', 'Visits due', CalendarDays, 'info', 'In the next 7 days'],
  ['overdue', 'Overdue visits', CircleAlert, 'danger', 'Date passed, still scheduled'],
  ['completed', 'Completed visits', Check, 'success', 'Visits documented'],
  ['missed', 'Missed visits', CalendarX2, 'danger', 'May need follow-up'],
  ['awaiting_review', 'Awaiting review', FileClock, 'warning', 'AI drafts for reviewers'],
];
const STATUSES = ['scheduled', 'completed', 'missed', 'cancelled'];

export default function DashboardPage() {
  const { user } = useAuth();
  const [study, setStudy] = useState('');
  const report = useApi(['report', study], () => api.followUpReport({ study_id: study }));
  const upcoming = useApi(['visits', 'upcoming', study], () => api.visits({ study_id: study, view: 'upcoming' }));
  const r = report.data;
  const maxCount = r ? Math.max(1, ...STATUSES.map(s => r[s] || 0)) : 1;

  return (
    <>
      <PageHeading title="Dashboard" description={`Welcome back, ${user.display_label}. Here is your study overview.`}>
        <StudySelect value={study} onChange={setStudy} />
      </PageHeading>

      <LoadState query={report}>
        {r && (
          <>
            <div className="stats-grid">
              {CARDS.map(([key, label, Icon, tone, caption]) => (
                <div className={`stat-card tone-${tone}`} key={key}>
                  <div className="stat-top"><span>{label}</span><span className="stat-icon"><Icon size={17} /></span></div>
                  <span className="stat-value">{r[key] ?? '—'}</span>
                  <div className="stat-caption">{caption}</div>
                </div>
              ))}
            </div>

            <div className="two-columns section-block">
              <section>
                <div className="section-header"><div><h2>Visits by status</h2><p>Counts come from the database</p></div></div>
                <div className="chart-card">
                  {STATUSES.map(s => (
                    <div className="chart-row" key={s}>
                      <span className="chart-label">{pretty(s)}</span>
                      <div className="chart-track" role="img" aria-label={`${pretty(s)}: ${r[s] ?? 0}`}>
                        <div className={`chart-bar chart-${s}`} style={{ width: `${((r[s] || 0) / maxCount) * 100}%` }} />
                      </div>
                      <span className="chart-count">{r[s] ?? 0}</span>
                    </div>
                  ))}
                </div>
              </section>
              <section>
                <div className="section-header"><div><h2>Needs attention</h2><p>Sorted by date, never by AI</p></div></div>
                <div className="attention-list">
                  <Link to="/coordinator/follow-ups" className="attention-item">
                    <span className="attention-icon"><Clock3 size={18} /></span>
                    <div><strong>Overdue visits</strong><p>{r.overdue} visit(s) need an update</p></div>
                    <ChevronRight size={15} />
                  </Link>
                  <Link to="/coordinator/follow-ups" className="attention-item">
                    <span className="attention-icon"><CalendarX2 size={18} /></span>
                    <div><strong>Missed visits</strong><p>{r.missed} missed visit(s) to follow up</p></div>
                    <ChevronRight size={15} />
                  </Link>
                  <Link to="/coordinator/follow-ups" className="attention-item">
                    <span className="attention-icon"><FileClock size={18} /></span>
                    <div><strong>Open follow-up actions</strong><p>{r.open_follow_up_actions} documented action(s)</p></div>
                    <ChevronRight size={15} />
                  </Link>
                </div>
              </section>
            </div>
          </>
        )}
      </LoadState>

      <section className="section-block">
        <div className="section-header">
          <div><h2>Upcoming visits</h2><p>Scheduled visits from today onwards</p></div>
          <Link className="btn btn-outline btn-sm" to="/coordinator/visits">Open visit schedule</Link>
        </div>
        <LoadState query={upcoming}>
          <DataTable
            columns={['Participant', 'Study', 'Date & time', 'Visit type', 'Status', '']}
            rows={upcoming.data?.slice(0, 8)}
            empty="No upcoming visits."
            renderRow={v => (
              <tr key={v.visit_id}>
                <td><Link to={`/coordinator/visits/${v.visit_id}`}>{v.participant_code}</Link></td>
                <td>{v.study_code}</td>
                <td>{dateTime(v.scheduled_for)}</td>
                <td>{pretty(v.visit_type)}</td>
                <td><div className="badge-pair"><Badge value={v.status} />{v.due_label && <Badge value={v.due_label} />}</div></td>
                <td><Link to={`/coordinator/visits/${v.visit_id}`} aria-label="Open visit"><ChevronRight size={16} /></Link></td>
              </tr>
            )}
          />
        </LoadState>
      </section>
    </>
  );
}