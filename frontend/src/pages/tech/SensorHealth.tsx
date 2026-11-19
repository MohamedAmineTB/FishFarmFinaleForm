// Sensor health (screen 42): one row per probe with a 6-hour sparkline and the pipeline's verdict.
import { useApi } from '../../api/realtime';
import { useTitle } from '../../App';
import { Spark } from '../../components/Charts';
import { useEnter } from '../../components/Home';
import { dayMonth } from '../../lib/format';
import { LoadError } from '../owner/Overview';
import { healthBadge } from '../owner/BasinDetail';

interface Probe {
  id: string;
  code: string;
  basin: string;
  label: string;
  health: string;
  note: string;
  spark: number[];
  calibrated: string | null;
}

export default function SensorHealth() {
  useTitle('Sensor health');
  const { data, error } = useApi<Probe[]>('/api/sensors', ['sensor_health', 'readings']);
  useEnter(!!data, 'sensors');
  if (!data) return <LoadError error={error} />;
  return (
    <div className="tile">
      <div className="section-title">
        <h3>Sensor health</h3>
        <span className="mini">Checked by the pipeline from rolling statistics on the last 24 h</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Probe</th>
              <th>Basin</th>
              <th>Measures</th>
              <th style={{ width: 140 }}>Last 6 h</th>
              <th>Status</th>
              <th>Evidence</th>
              <th>Calibrated</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => {
              const [cls, label] = healthBadge(s.health);
              const color = s.health === 'ok' ? '#1d6f6a' : cls === 'b-critical' ? '#d6453d' : '#d98a1c';
              return (
                <tr key={s.id}>
                  <td className="mono">{s.code}</td>
                  <td>{s.basin}</td>
                  <td>{s.label}</td>
                  <td>
                    <Spark values={s.spark} color={color} />
                  </td>
                  <td>
                    <span className={`badge ${cls}`}>{label}</span>
                  </td>
                  <td className="mini">{s.note}</td>
                  <td className="mono">{s.calibrated ? dayMonth(s.calibrated) : '–'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
