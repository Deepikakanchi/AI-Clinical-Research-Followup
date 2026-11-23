/*
 * pages/coordinator/FollowUpsPage.jsx - Outstanding work.
 * Uses Person 2's endpoint GET /api/reports/follow-up-items:
 *   missed_or_overdue_visits, notes_with_actions, flagged_summaries.
 * Ordered by date only: no urgency score and no AI judgement.  US-14, US-26.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { api } from '@/api/client';
import {
  Badge, DataTable, Empty, LoadState, PageHeading, StudySelect, dateTime, pretty, useApi,
} from '@/components/common/ui';

export default function FollowUpsPage() {
  const [study, setStudy] = useState('');
  const items = useApi(['follow-up-items', study], () => api.followUpItems({ study_id: study }));
  const data = items.data;

  return (
    <>
      <PageHeading title="Follow-ups" description="Missed and overdue visits, open actions and reviewer flags. Ordered by date only.">
        <StudySelect value={study} onChange={setStudy} />
      </PageHeading>

      <LoadState query={items}>
        {data && (
          <>
            <section>
              <div className="section-header"><h2>Missed and overdue visits</h2></div>
              <DataTable
                columns={['Participant', 'Study', 'Visit date', 'Visit type', 'Status', '']}
                rows={data.missed_or_overdue_visits}
                empty="No missed or overdue visits."
                renderRow={v => (
                  <tr key={v.visit_id}>
                    <td><strong>{v.participant_code}</strong></td>
                    <td>{v.study_code}</td>
                    <td>{dateTime(v.scheduled_for)}</td>
                    <td>{pretty(v.visit_type)}</td>
                    <td><div className="badge-pair"><Badge value={v.status} />{v.due_label && <Badge value={v.due_label} />}</div></td>
                    <td><Link to={`/coordinator/visits/${v.visit_id}`}>Open visit<ArrowRight size={14} /></Link></td>
                  </tr>
                )}
              />
            </section>

            <div className="followup-grid section-block">
              <section>
                <h2>Open follow-up actions</h2>
                {data.notes_with_actions?.length ? data.notes_with_actions.map(n => (
                  <div className="source-note" key={n.note_id}>
                    <small>{n.participant_code ? `${n.participant_code} · ` : ''}{dateTime(n.visit_date || n.scheduled_for || n.created_at)}</small>
                    <ul>{(n.follow_up_actions || []).map((a, i) => <li key={i}>{a}</li>)}</ul>
                    <Link className="back-link" to={`/coordinator/visits/${n.visit_id}`}>Open source visit<ArrowRight size={13} /></Link>
                  </div>
                )) : <Empty text="No open follow-up actions." />}
              </section>

              <section>
                <h2>Flagged by a reviewer</h2>
                {data.flagged_summaries?.length ? data.flagged_summaries.map(f => (
                  <div className="approved-box" key={f.summary_id}>
                    <span className="eyebrow">FLAGGED FOR QUALIFIED FOLLOW-UP</span>
                    <p><strong>{f.participant_code || `Summary ${f.summary_id}`}</strong>
                      {f.visit_date ? ` · visit ${dateTime(f.visit_date)}` : ''}</p>
                    <small className="muted">{f.reviewer_code}{f.reviewed_at ? ` · ${dateTime(f.reviewed_at)}` : ''}</small>
                    {f.visit_id && <div><Link className="back-link" to={`/coordinator/visits/${f.visit_id}`}>Open visit<ArrowRight size={13} /></Link></div>}
                  </div>
                )) : <Empty text="No summaries flagged for follow-up." />}
              </section>
            </div>
          </>
        )}
      </LoadState>
    </>
  );
}