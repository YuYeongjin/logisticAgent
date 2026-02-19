import { useState } from 'react';
import './App.css';
import View from "./view/chat/View.js"
import Topbar from './view/Component/Topbar.js';
import Traning from './view/traning/Traning.js';
import Dashboard from './view/dashboard/Dashboard.js';
function App() {
  const [viewComponent, setViewComponent] = useState('');
  return (
    <div className="App">
      <Topbar setViewComponent={setViewComponent} />

      {
        viewComponent === 'traning' ?
          <Traning />
          :
          viewComponent === 'dashboard' ?
            <Dashboard />
            :
            <View />
      }
    </div>
  );
}

export default App;
