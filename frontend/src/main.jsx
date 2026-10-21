import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import PliesDashboard from './PliesDashboard.jsx';
import { isPliesPath } from './plies.js';
import './styles.css';

// The Plies dashboard is its own page at /plies; every other address shows the review screen.
const Page = isPliesPath(window.location.pathname) ? PliesDashboard : App;
createRoot(document.getElementById('root')).render(<React.StrictMode><Page /></React.StrictMode>);
