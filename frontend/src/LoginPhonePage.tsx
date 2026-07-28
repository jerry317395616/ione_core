import { useCallback, useState } from 'react'
import {
  Button,
  Card,
  Form,
  Input,
  NoticeBar,
  Space,
  Tag,
  Toast,
} from 'antd-mobile'
import {
  AppOutline,
  CheckShieldOutline,
  EyeInvisibleOutline,
  EyeOutline,
  LockOutline,
  UserOutline,
} from 'antd-mobile-icons'
import { loginToFrappe } from './lib/frappeRequest'

export interface AuthUser {
  username: string
  fullName: string
}

interface LoginPhonePageProps {
  onComplete: (user: AuthUser) => void
}

export default function LoginPhonePage({ onComplete }: LoginPhonePageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = useCallback(async () => {
    const account = username.trim()
    setError('')

    if (!account || !password) {
      const message = '请输入账号和密码'
      setError(message)
      return
    }

    setLoading(true)
    try {
      const user = await loginToFrappe(account, password)
      setPassword('')
      Toast.show({ icon: 'success', content: '登录成功' })
      onComplete(user)
    } catch (loginError) {
      const message = loginError instanceof Error ? loginError.message : '登录失败，请稍后再试'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [onComplete, password, username])

  return (
    <div className="auth-page">
      <div className="auth-shell auth-shell-login">
        <div className="auth-brand">
          <div className="auth-logo" aria-hidden="true">
            <AppOutline />
          </div>
          <h1>I-ONE</h1>
          <p>一人公司智能工作台</p>
        </div>

        <Card className="auth-card auth-login-card">
          <div className="auth-card-heading">
            <div>
              <div className="auth-section-title">登录工作台</div>
              <div className="auth-section-desc">使用美妍伊人管理平台账号</div>
            </div>
            <Tag color="primary" fill="outline">Frappe</Tag>
          </div>

          {error && (
            <NoticeBar
              color="alert"
              wrap
              closeable
              content={error}
              onClose={() => setError('')}
              className="auth-notice"
            />
          )}

          <Form layout="vertical" onFinish={handleLogin}>
            <Form.Item
              label={<span className="auth-field-label"><UserOutline />账号</span>}
            >
              <Input
                value={username}
                onChange={setUsername}
                placeholder="邮箱或 Frappe 用户名"
                clearable
                autoFocus
                autoComplete="username"
                onEnterPress={handleLogin}
              />
            </Form.Item>
            <Form.Item
              label={<span className="auth-field-label"><LockOutline />密码</span>}
            >
              <div className="auth-password-field">
                <Input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={setPassword}
                  placeholder="请输入密码"
                  autoComplete="current-password"
                  onEnterPress={handleLogin}
                />
                <Button
                  type="button"
                  fill="none"
                  size="mini"
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  onClick={() => setShowPassword(value => !value)}
                  className="auth-password-toggle"
                >
                  {showPassword ? <EyeInvisibleOutline /> : <EyeOutline />}
                </Button>
              </div>
            </Form.Item>

            <Button
              block
              color="primary"
              size="large"
              type="submit"
              loading={loading}
              disabled={!username.trim() || !password}
              className="auth-primary-button"
            >
              登录
            </Button>
          </Form>

          <Space block justify="between" align="center" className="auth-login-links">
            <span><CheckShieldOutline /> 统一身份认证</span>
            <a href="https://manager.myyr.top/login#forgot" target="_blank" rel="noreferrer">
              忘记密码
            </a>
          </Space>
        </Card>

        <div className="auth-manager-link">
          账号由 <a href="https://manager.myyr.top/" target="_blank" rel="noreferrer">manager.myyr.top</a> 统一管理
        </div>
      </div>
    </div>
  )
}
