import React, { useState } from "react";

export default function Topbar({ setViewComponent }) {
    const [currentTab, setCurrentTab] = useState('prompt');

    const handleTabClick = (tab) => {
        setCurrentTab(tab);
        setViewComponent(tab);
    };

    return (
        <nav style={styles.navBar}>
            <div style={styles.tabContainer}>
                <div style={styles.statusDot}>veneta AI agent</div>
                <button
                    onClick={() => handleTabClick('prompt')}
                    style={{
                        ...styles.tabButton,
                        borderBottom: currentTab === 'prompt' ? '3px solid #007bff' : '3px solid transparent',
                        color: currentTab === 'prompt' ? '#007bff' : '#666',
                        fontWeight: currentTab === 'prompt' ? '700' : '500',
                    }}
                >
                    Prompt
                </button>
                <button
                    onClick={() => handleTabClick('dashboard')}
                    style={{
                        ...styles.tabButton,
                        borderBottom: currentTab === 'dashboard' ? '3px solid #007bff' : '3px solid transparent',
                        color: currentTab === 'dashboard' ? '#007bff' : '#666',
                        fontWeight: currentTab === 'dashboard' ? '700' : '500',
                    }}
                >
                    Dashboard
                </button>
                <button
                    onClick={() => handleTabClick('traning')}
                    style={{
                        ...styles.tabButton,
                        borderBottom: currentTab === 'traning' ? '3px solid #007bff' : '3px solid transparent',
                        color: currentTab === 'traning' ? '#007bff' : '#666',
                        fontWeight: currentTab === 'traning' ? '700' : '500',
                    }}
                >
                    Training
                </button>
            </div>

        </nav>
    );
}

const styles = {
    navBar: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0 20px',
        backgroundColor: '#fff',
        height: '60px',
        borderBottom: '1px solid #f0f0f0',
    },
    tabContainer: {
        display: 'flex',
        gap: '20px',
        height: '100%',
    },
    tabButton: {
        background: 'none',
        border: 'none',
        padding: '0 10px',
        fontSize: '16px',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        outline: 'none',
        display: 'flex',
        alignItems: 'center',
        height: '100%',
    },
    statusDot: {
        display: 'flex',
        fontSize: '20px',
        color: '#28a745',
        fontWeight: '600',
        justifyContent: 'center',
        alignItems: 'center'
    }
};