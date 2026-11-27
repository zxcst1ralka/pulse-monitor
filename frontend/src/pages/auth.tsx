import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { authenticate } from '../api/client'
import { Brand } from '../components/ui'
import { Button } from '../components/ui/button'
import { useSession } from '../hooks/session'

export function AuthPage({ registerAccount }: { registerAccount: boolean }) {
  const [visible, setVisible] = useState(false)
  const { user } = useSession()
  const navigate = useNavigate()
  const schema = z.object({
    name: registerAccount ? z.string().trim().min(1, 'Введите имя').max(80) : z.string().optional(),
    email: z.email('Введите корректный email'),
    password: z.string().min(registerAccount ? 8 : 1, registerAccount ? 'Минимум 8 символов' : 'Введите пароль').max(256),
  })
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { name: '', email: '', password: '' },
  })
  if (user) return <Navigate to="/app" replace />
  return <main className="auth-page">
    <header><Brand /><Button asChild variant="ghost" size="small"><Link to="/">На главную</Link></Button></header>
    <section className="auth-card">
      <div className="auth-icon"><img src="/pulse.svg" alt="" width="42" height="42" /></div>
      <h1>{registerAccount ? 'Создайте аккаунт' : 'Вход в PulseMonitor'}</h1>
      <p>{registerAccount ? 'Добавьте первый сервис и следите за его доступностью.' : 'Откройте рабочее пространство мониторинга.'}</p>
      <form onSubmit={handleSubmit(async values => {
        try {
          await authenticate(registerAccount ? '/auth/register' : '/auth/login',
            registerAccount ? values : { email: values.email, password: values.password })
          navigate('/app', { replace: true })
        } catch (error) {
          setError('root', { message: error instanceof Error ? error.message : 'Попробуйте ещё раз' })
        }
      })} noValidate>
        {registerAccount && <label>Имя<input autoComplete="name" placeholder="Ваше имя" {...register('name')} />
          {errors.name && <small className="field-error">{errors.name.message}</small>}</label>}
        <label>Email<input autoComplete="email" type="email" placeholder="name@example.com" {...register('email')} />
          {errors.email && <small className="field-error">{errors.email.message}</small>}</label>
        <label>Пароль<span className="password-field"><input type={visible ? 'text' : 'password'}
          autoComplete={registerAccount ? 'new-password' : 'current-password'} {...register('password')} />
          <button type="button" aria-label={visible ? 'Скрыть пароль' : 'Показать пароль'} onClick={() => setVisible(!visible)}>
            {visible ? <EyeOff size={17} /> : <Eye size={17} />}</button></span>
          {errors.password && <small className="field-error">{errors.password.message}</small>}</label>
        {errors.root && <p className="field-error" role="alert">{errors.root.message}</p>}
        <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Подождите…' : registerAccount ? 'Создать аккаунт' : 'Войти'}</Button>
      </form>
      <div className="auth-switch">{registerAccount ? 'Уже есть аккаунт?' : 'Впервые в PulseMonitor?'}{' '}
        <Link to={registerAccount ? '/login' : '/register'}>{registerAccount ? 'Войти' : 'Зарегистрироваться'}</Link>
      </div>
    </section>
  </main>
}
