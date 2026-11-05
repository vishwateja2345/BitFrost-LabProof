import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) return <div className="error-banner" role="alert"><strong>Viewer error.</strong> {this.state.error.message}</div>;
    return this.props.children;
  }
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');
ReactDOM.createRoot(root).render(<React.StrictMode><ErrorBoundary><App /></ErrorBoundary></React.StrictMode>);
