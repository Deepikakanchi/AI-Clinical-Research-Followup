/*
 * main.jsx - Frontend entry point.
 * Sets up the router, the data-loading client and the global styles.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App.jsx';
import { AuthProvider } from './components/common/AuthContext.jsx';
import './styles.css';

const queryClient = new QueryClient({
  defaultOptions: {
    // Never retry automatically: errors such as 403/404 are real answers, not glitches.
    queries: { retry: false, refetchOnWindowFocus: false },
  },
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);