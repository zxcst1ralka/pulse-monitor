import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { IncidentStatus, Pagination, Status, percent } from './ui'

describe('monitor outputs', () => {
  it('makes failure and paused states readable without relying on color', () => {
    expect(renderToStaticMarkup(<Status status="down" />)).toContain('Недоступен')
    expect(renderToStaticMarkup(<Status status="paused" />)).toContain('На паузе')
    expect(renderToStaticMarkup(<IncidentStatus status="resolved" />)).toContain('Закрыт')
  })

  it('distinguishes no completed checks from zero uptime', () => {
    expect(percent(null)).toBe('Нет данных')
    expect(percent(0)).toBe('0%')
  })

  it('disables pagination at both ends of the results', () => {
    expect(renderToStaticMarkup(<Pagination offset={0} size={10} count={4} change={() => {}} />)).toBe('')
    const last = renderToStaticMarkup(<Pagination offset={10} size={10} count={4} change={() => {}} />)
    expect(last).toContain('Страница 2')
    expect(last).toMatch(/disabled="" aria-label="Следующая страница"/)
  })
})
