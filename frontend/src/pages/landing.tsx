import { Activity, BellRing, ChartNoAxesCombined, CircleCheck, Clock3, Globe, LayoutDashboard, Radio, ShieldCheck, Siren, Waypoints } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from '../components/ui'
import { Button } from '../components/ui/button'

const features = [
  { Icon: Globe, title: 'HTTP и HTTPS', text: 'Проверяйте сайты, API и наличие ключевого слова в ответе.' },
  { Icon: ChartNoAxesCombined, title: 'История доступности', text: 'Смотрите долю успешных проверок, задержку и историю сбоев.' },
  { Icon: BellRing, title: 'Уведомления в Telegram', text: 'Получайте сообщение при подтверждённом сбое и восстановлении.' },
  { Icon: ShieldCheck, title: 'Контроль TLS', text: 'Следите за валидностью сертификатов и получайте предупреждения об истечении.' },
  { Icon: Radio, title: 'Статус-страницы', text: 'Показывайте клиентам доступность выбранных сервисов и историю инцидентов.' },
  { Icon: Waypoints, title: 'Развёртывание на своём сервере', text: 'Запускайте PulseMonitor через Docker Compose и храните результаты в PostgreSQL.' },
]

function DashboardPreview() {
  return <figure className="product-preview" aria-label="Пример интерфейса PulseMonitor">
    <div className="preview-sidebar" aria-hidden="true">
      <div className="preview-brand"><img src="/pulse.svg" alt="" width="26" height="26" />PulseMonitor</div>
      <span>РАБОЧЕЕ ПРОСТРАНСТВО</span>
      <div className="preview-current"><LayoutDashboard size={15} /> Обзор</div>
      <div><Globe size={15} /> Мониторы</div><div><Siren size={15} /> Инциденты</div><div><Radio size={15} /> Статус-страницы</div>
    </div>
    <div className="preview-content">
      <div className="preview-top"><span>Рабочее пространство <b>/</b> Обзор</span><span>Демонстрационные данные</span></div>
      <div className="preview-heading"><div><h2>Обзор</h2><p>Доступность и производительность сервисов</p></div>
        <span className="preview-add">+ Новый монитор</span></div>
      <div className="preview-metrics">
        <div><Globe size={15} /><span>Мониторы</span><strong>06</strong></div>
        <div><CircleCheck size={15} /><span>Работают</span><strong>05</strong></div>
        <div><Activity size={15} /><span>Uptime · 24 ч</span><strong>99,8<span>%</span></strong></div>
        <div><Clock3 size={15} /><span>Средний ответ</span><strong>142<span> мс</span></strong></div>
      </div>
      <div className="preview-panels">
        <div className="preview-graph">
          <div><b>Время ответа</b><span>Последние 24 часа</span></div>
          <svg viewBox="0 0 580 116" role="img" aria-label="Пример графика времени ответа" preserveAspectRatio="none">
            <defs><linearGradient id="preview-area" x2="0" y2="1"><stop stopColor="#7772ff" stopOpacity=".32"/><stop offset="100%" stopColor="#7772ff" stopOpacity=".015"/></linearGradient></defs>
            <path d="M0 20H580M0 48H580M0 76H580M0 104H580" stroke="#292735" strokeDasharray="3 5"/>
            <path d="M0 89L19 85 42 91 62 76 83 80 104 51 123 68 145 80 167 68 190 73 212 54 231 58 256 74 279 61 301 71 327 42 350 25 369 50 392 63 415 48 441 75 467 57 488 60 510 36 531 53 556 47 580 32V116H0Z" fill="url(#preview-area)"/>
            <path d="M0 89L19 85 42 91 62 76 83 80 104 51 123 68 145 80 167 68 190 73 212 54 231 58 256 74 279 61 301 71 327 42 350 25 369 50 392 63 415 48 441 75 467 57 488 60 510 36 531 53 556 47 580 32" fill="none" stroke="#918cff" strokeWidth="2"/>
          </svg>
          <div className="preview-time"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>Сейчас</span></div>
        </div>
        <div className="preview-services"><b>Сервисы</b>
          <div><span><Globe size={13} /> Production API</span><i /></div>
          <div><span><Globe size={13} /> Основной сайт</span><i /></div>
          <div><span><Globe size={13} /> Вебхуки</span><i /></div>
          <div><span><Globe size={13} /> Payment Gateway</span><i className="unavailable" /></div>
        </div>
      </div>
    </div>
  </figure>
}

export function Landing() {
  return <div className="landing">
    <header className="landing-header"><div className="landing-nav">
      <Brand />
      <nav aria-label="О продукте"><a href="#features">Возможности</a><a href="#workflow">Как это работает</a><a href="/api/docs">API</a></nav>
      <div className="landing-actions"><Button asChild variant="ghost" size="small"><Link to="/login">Войти</Link></Button>
        <Button asChild size="small"><Link to="/register">Регистрация</Link></Button></div>
    </div></header>
    <main>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-halo" aria-hidden="true"><i /><i /><i /></div>
        <div className="hero-copy">
          <h1 id="hero-title">Контролируйте доступность<br className="hero-break" /> <span>ваших сервисов</span></h1>
          <p>Проверяйте сайты и API, получайте уведомления о сбоях в Telegram и делитесь статусом сервисов с клиентами.</p>
          <div className="hero-actions">
            <Button asChild><Link to="/register">Начать мониторинг</Link></Button>
            <Button asChild variant="secondary"><a href="#preview"><LayoutDashboard size={16} /> Смотреть дашборд</a></Button>
          </div>
        </div>
        <div className="preview-wrap" id="preview"><DashboardPreview /></div>
      </section>
      <section className="landing-section" id="features">
        <h2>Что отслеживает PulseMonitor</h2>
        <div className="feature-grid">{features.map(({ Icon, title, text }) => <article className="feature" key={title}>
          <div className="feature-icon"><Icon size={20} /></div><h3>{title}</h3><p>{text}</p>
        </article>)}</div>
      </section>
      <section className="landing-section landing-workflow" id="workflow">
        <div><h2>От адреса до первой проверки</h2><p>Добавьте сервис, и PulseMonitor начнёт собирать историю доступности.</p>
          <Button asChild><Link to="/register">Создать аккаунт</Link></Button></div>
        <ol>
          <li><Globe size={20} /><div><b>Добавьте сайт или API</b><p>Введите публичный URL и укажите ожидаемый HTTP-код.</p></div></li>
          <li><Clock3 size={20} /><div><b>Выберите интервал</b><p>Планировщик сможет проверять сервис каждую минуту.</p></div></li>
          <li><BellRing size={20} /><div><b>Подключите Telegram</b><p>Бот сообщит о сбое после двух неуспешных проверок подряд.</p></div></li>
        </ol>
      </section>
    </main>
    <footer className="landing-footer"><Brand /><a href="/api/docs">Документация API</a><span>MIT · © 2026 zxcst1ralka</span></footer>
  </div>
}
