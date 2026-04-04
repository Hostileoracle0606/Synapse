import React from 'react';
import {
  Zap, HelpCircle, Bell, User, FileText,
  Send, Crosshair, Plus, Minus, RotateCcw, MoreVertical,
  Sparkles, BookOpen, Upload, ChevronRight, MessageSquare
} from 'lucide-react';

export default function App() {
  return (
    <div className="h-screen w-screen bg-[#f0f4f9] text-[#1f1f1f] font-sans flex flex-col overflow-hidden">
      {/* Global Wrapper - Google's signature light blue-gray background */}

      {/* Top Navigation - Blends with background, minimalist */}
      <header className="flex items-center justify-between px-6 py-4 z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
            <BookOpen className="w-5 h-5 text-[#0b57d0]" />
          </div>
          <h1 className="font-normal text-xl tracking-tight text-[#1f1f1f]">
            Synapse Notebook
          </h1>
        </div>
        <div className="flex items-center gap-4 text-[#444746]">
          <button className="w-10 h-10 rounded-full hover:bg-black/5 flex items-center justify-center transition-colors">
             <HelpCircle className="w-5 h-5" />
          </button>
          <button className="w-10 h-10 rounded-full hover:bg-black/5 flex items-center justify-center transition-colors relative">
             <Bell className="w-5 h-5" />
             <span className="absolute top-2 right-2 w-2 h-2 bg-[#b3261e] rounded-full border border-[#f0f4f9]"></span>
          </button>
          <button className="w-8 h-8 rounded-full bg-[#0b57d0] text-white flex items-center justify-center font-medium text-sm ml-2">
            U
          </button>
        </div>
      </header>

      {/* Main Layout Workspace */}
      <main className="flex-1 flex gap-4 px-4 pb-4 overflow-hidden z-10">

        {/* LEFT COLUMN: Sources (Data Ingestion) */}
        <section className="w-80 flex flex-col gap-4 overflow-y-auto pr-1 pb-4 no-scrollbar">

          <div className="flex items-center justify-between px-2">
             <h2 className="text-sm font-medium text-[#1f1f1f]">Sources</h2>
             <button className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center transition-colors">
               <Plus className="w-5 h-5 text-[#444746]" />
             </button>
          </div>

          {/* Add Source Area */}
          <div className="group bg-white rounded-3xl p-4 flex items-center gap-4 cursor-pointer hover:shadow-md transition-all border border-transparent hover:border-blue-100">
            <div className="w-12 h-12 rounded-2xl bg-[#f0f4f9] group-hover:bg-blue-50 flex items-center justify-center transition-colors shrink-0">
              <Upload className="w-6 h-6 text-[#0b57d0]" />
            </div>
            <div>
              <p className="text-sm font-medium text-[#1f1f1f]">Add source</p>
              <p className="text-xs text-[#444746]">PDF, Text, or URL</p>
            </div>
          </div>

          {/* Knowledge Base / Sources List */}
          <div className="flex flex-col gap-2 mt-2">
            <KnowledgeDoc title="AI in Healthcare Report 2024" summary="32 pages • 14 mins ago" />
            <KnowledgeDoc title="Legal Contract - Project Alpha" summary="12 pages • Processing..." active />
            <KnowledgeDoc title="Market Analysis Q3" summary="Webpage • 2 hrs ago" />
            <KnowledgeDoc title="Technical Manual v2.1" summary="Error reading file" error />
          </div>
        </section>

        {/* CENTER COLUMN: Visualization - The "Studio/Canvas" */}
        <section className="flex-1 bg-white rounded-[2rem] relative overflow-hidden flex flex-col shadow-sm border border-[#e0e2e0]">
          <div className="absolute top-6 left-6 z-10 bg-white/80 backdrop-blur-md py-1.5 px-4 rounded-full border border-[#e0e2e0] shadow-sm">
            <h2 className="text-sm font-medium text-[#1f1f1f] flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#0b57d0]" />
              Concept Graph
            </h2>
          </div>

          {/* Simulated Force Graph (SVG) - Material Colors */}
          <div className="flex-1 w-full h-full cursor-grab active:cursor-grabbing bg-[#fafafa]">
            <NetworkGraphMockup />
          </div>

          {/* Popover Card - Clean Material Card */}
          <div className="absolute top-1/2 left-1/2 transform translate-x-12 -translate-y-12 w-[340px] bg-white rounded-3xl p-6 z-20 shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-[#e0e2e0]">
            <div className="flex items-start justify-between mb-2">
               <h3 className="text-base font-medium text-[#1f1f1f]">Neural Networks</h3>
               <button className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center -mr-2 -mt-2">
                  <MoreVertical className="w-5 h-5 text-[#444746]" />
               </button>
            </div>

            <div className="space-y-3 text-sm text-[#444746] mb-6">
              <p className="flex gap-2">
                <span className="font-medium text-[#1f1f1f] w-16">Type:</span>
                <span className="bg-[#f0f4f9] px-2 py-0.5 rounded-md text-xs font-medium text-[#0b57d0]">Concept</span>
              </p>
              <p className="flex gap-2">
                <span className="font-medium text-[#1f1f1f] w-16">Related:</span>
                <span>Deep Learning, ML</span>
              </p>
              <div className="pt-3 border-t border-[#f0f4f9]">
                 <p className="leading-relaxed">
                   A series of algorithms that endeavor to recognize underlying relationships in a set of data through a process that mimics the way the human brain operates.
                 </p>
              </div>
            </div>

            <div className="flex gap-3">
              <button className="flex-1 text-[#0b57d0] hover:bg-blue-50 font-medium text-sm py-2 rounded-full transition-colors border border-[#c2e7ff]">
                View Source
              </button>
              <button className="flex-1 bg-[#0b57d0] hover:bg-[#0842a0] text-white font-medium text-sm py-2 rounded-full transition-colors shadow-sm">
                Expand
              </button>
            </div>
          </div>

          {/* Graph Controls - Clean Pill */}
          <div className="absolute bottom-6 right-6 flex bg-white rounded-full overflow-hidden shadow-sm border border-[#e0e2e0] p-1">
            <ControlButton icon={<Crosshair size={18} />} />
            <ControlButton icon={<Plus size={18} />} />
            <ControlButton icon={<Minus size={18} />} />
            <ControlButton icon={<RotateCcw size={18} />} />
          </div>
        </section>

        {/* RIGHT COLUMN: AI Chat & Queries */}
        <section className="w-[380px] flex flex-col bg-white rounded-[2rem] overflow-hidden shadow-sm border border-[#e0e2e0] relative">

          <div className="flex items-center px-6 py-5 border-b border-[#f0f4f9] z-10">
             <h2 className="text-base font-medium text-[#1f1f1f] flex items-center gap-2">
               <MessageSquare className="w-5 h-5 text-[#0b57d0]" />
               Notebook Guide
             </h2>
          </div>

          {/* Chat History */}
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6 no-scrollbar bg-white">

            {/* Suggested Chips */}
            <div className="flex flex-wrap gap-2 mb-2">
               <span className="bg-[#f0f4f9] hover:bg-[#e1e3e1] cursor-pointer text-[#1f1f1f] text-xs font-medium px-4 py-2 rounded-full border border-transparent transition-colors">Help me understand...</span>
               <span className="bg-[#f0f4f9] hover:bg-[#e1e3e1] cursor-pointer text-[#1f1f1f] text-xs font-medium px-4 py-2 rounded-full border border-transparent transition-colors">Summarize sources</span>
            </div>

            {/* User Message - Soft gray pill */}
            <div className="flex justify-end">
              <div className="bg-[#f0f4f9] text-[#1f1f1f] text-[15px] py-3 px-5 rounded-3xl rounded-tr-md shadow-none max-w-[85%]">
                Identify key entities in the latest Q3 report.
              </div>
            </div>

            {/* AI Response - Clean white with icon */}
            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
                 <Sparkles className="w-4 h-4 text-[#0b57d0]" />
              </div>
              <div className="text-[#1f1f1f] text-[15px] pt-1">
                <p className="mb-3">Based on the Q3 Analysis, here are the key entities observed in your sources:</p>
                <ul className="list-disc pl-5 mb-4 space-y-1.5 text-[#444746]">
                  <li><strong>Competitor X:</strong> Mentioned 14 times regarding market share.</li>
                  <li><strong>Market Trends:</strong> Focus on shift towards edge computing.</li>
                  <li><strong>Consumer Behavior:</strong> 22% increase in preference for privacy-first tools.</li>
                </ul>
                <div className="bg-[#f8f9fa] rounded-2xl p-4 border border-[#e0e2e0]">
                   <p className="text-sm text-[#444746] flex items-center gap-2">
                     <FileText className="w-4 h-4" />
                     Referenced in: <span className="font-medium text-[#0b57d0] cursor-pointer hover:underline">Market Analysis Q3</span>
                   </p>
                </div>
              </div>
            </div>

          </div>

          {/* Ask Input - Floating Pill style */}
          <div className="p-4 bg-white border-t border-[#f0f4f9]">
            <div className="relative flex items-center bg-[#f0f4f9] rounded-full px-2 py-1 focus-within:bg-white focus-within:shadow-[0_0_0_1px_#0b57d0] transition-all">
              <input
                type="text"
                placeholder="Ask about your sources..."
                className="w-full bg-transparent pl-4 pr-12 py-3 text-[15px] focus:outline-none text-[#1f1f1f] placeholder:text-[#444746]"
              />
              <button className="absolute right-2 w-10 h-10 flex items-center justify-center text-white bg-[#0b57d0] hover:bg-[#0842a0] rounded-full transition-colors disabled:opacity-50">
                 <Send className="w-4 h-4 ml-0.5" />
              </button>
            </div>
            <p className="text-center text-[11px] text-[#444746] mt-3">
               Notebook guide may produce inaccurate information about people, places, or facts.
            </p>
          </div>
        </section>

      </main>

      <style dangerouslySetInnerHTML={{__html: `
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #dadce0; border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: #bdc1c6; }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      `}} />
    </div>
  );
}

// Sub-components

function KnowledgeDoc({ title, summary, active = false, error = false }) {
  let indicatorColor = "bg-[#e0e2e0]";
  if (active) indicatorColor = "bg-[#fbbc04] animate-pulse";
  if (error) indicatorColor = "bg-[#ea4335]";

  return (
    <div className={`group bg-white rounded-3xl p-4 flex flex-col gap-1 cursor-pointer transition-all border ${active ? 'border-[#c2e7ff] bg-blue-50/30' : 'border-transparent hover:bg-black/[0.02]'}`}>
      <div className="flex items-start gap-3">
        <div className="mt-1 relative flex items-center justify-center shrink-0">
           <FileText className={`w-5 h-5 ${error ? 'text-[#ea4335]' : 'text-[#0b57d0]'}`} />
        </div>
        <div className="flex-1 overflow-hidden">
          <h3 className="text-sm font-medium text-[#1f1f1f] truncate pr-2">{title}</h3>
          <p className="text-xs text-[#444746] mt-0.5 flex items-center gap-1.5">
             <span className={`w-1.5 h-1.5 rounded-full ${indicatorColor}`}></span>
             {summary}
          </p>
        </div>
      </div>
    </div>
  );
}

function ControlButton({ icon }) {
  return (
    <button className="w-10 h-10 flex items-center justify-center text-[#444746] hover:bg-[#f0f4f9] rounded-full transition-all">
      {icon}
    </button>
  );
}

// 3D Force-Directed Graph Engine (Material 3 Theme)
function NetworkGraphMockup() {
  const canvasRef = React.useRef(null);
  const animationRef = React.useRef(null);
  const isDragging = React.useRef(false);
  const previousMouse = React.useRef({ x: 0, y: 0 });
  const rotation = React.useRef({ x: 0, y: 0 });

  // Using Google's brand colors
  const colors = {
    blue: '#4285F4', red: '#EA4335', yellow: '#FBBC05',
    green: '#34A853', purple: '#A142F4', teal: '#24C1E0'
  };

  const nodesData = [
    { id: 1, label: 'Neural Networks', r: 32, color: colors.blue, elevated: true },
    { id: 2, label: 'Machine Learning', r: 22, color: colors.blue },
    { id: 3, label: 'Deep Learning', r: 20, color: colors.teal },
    { id: 4, label: 'NLP', r: 18, color: colors.purple },
    { id: 5, label: 'Data Privacy', r: 16, color: colors.red },
    { id: 6, label: 'Startups', r: 12, color: colors.yellow },
    { id: 7, label: 'Regulation', r: 14, color: colors.red },
    { id: 8, label: 'Neural Networks', r: 10, color: colors.blue },
    { id: 9, label: 'Startups', r: 12, color: colors.yellow },
    { id: 10, label: 'Data Privacy', r: 12, color: colors.red },
    { id: 11, label: 'Innovation', r: 14, color: colors.green },
    { id: 12, label: 'Data Privacy', r: 10, color: colors.red },
    { id: 13, label: 'Innovation', r: 12, color: colors.green },
    { id: 14, label: 'Regulation', r: 14, color: colors.red },
    { id: 15, label: 'Deep Learning', r: 12, color: colors.teal },
    { id: 16, label: 'Synapse Platform', r: 16, color: colors.purple },
    { id: 17, label: 'Doc Intel', r: 12, color: colors.teal },
    { id: 18, label: 'Formulation', r: 10, color: colors.purple },
    { id: 19, label: 'Models', r: 10, color: colors.blue },
  ];

  const linksData = [
    [1, 2], [1, 3], [1, 4], [1, 5],
    [2, 6], [2, 7], [2, 8], [2, 12], [2, 18],
    [3, 11], [3, 13], [3, 14], [3, 19],
    [4, 8], [4, 9], [4, 18],
    [5, 15], [5, 16], [5, 19],
    [16, 17], [7, 10], [6, 12]
  ];

  React.useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    // Initialize nodes with random 3D coordinates and zero velocity
    const nodes = nodesData.map(n => ({
      ...n,
      x: (Math.random() - 0.5) * 300,
      y: (Math.random() - 0.5) * 300,
      z: (Math.random() - 0.5) * 300,
      vx: 0, vy: 0, vz: 0
    }));

    // Physics constants
    const REPULSION = 12000;
    const SPRING_LENGTH = 120;
    const SPRING_K = 0.03;
    const DAMPING = 0.85;

    const animate = () => {
      // Handle canvas resizing dynamically
      if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;
      }
      const width = canvas.width;
      const height = canvas.height;

      // 1. Auto-rotation if the user isn't interacting
      if (!isDragging.current) {
        rotation.current.y -= 0.003;
      }

      // 2. Physics Engine: Calculate repulsive forces (Coulomb's Law)
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dz = nodes[j].z - nodes[i].z;
          let distSq = dx*dx + dy*dy + dz*dz;
          if (distSq === 0) distSq = 0.01;
          const dist = Math.sqrt(distSq);

          const force = REPULSION / distSq;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          const fz = (dz / dist) * force;

          nodes[i].vx -= fx; nodes[i].vy -= fy; nodes[i].vz -= fz;
          nodes[j].vx += fx; nodes[j].vy += fy; nodes[j].vz += fz;
        }
      }

      // 3. Physics Engine: Calculate attractive spring forces (Hooke's Law)
      linksData.forEach(link => {
        const source = nodes.find(n => n.id === link[0]);
        const target = nodes.find(n => n.id === link[1]);
        if (!source || !target) return;

        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dz = target.z - source.z;
        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.01;

        const force = (dist - SPRING_LENGTH) * SPRING_K;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        const fz = (dz / dist) * force;

        source.vx += fx; source.vy += fy; source.vz += fz;
        target.vx -= fx; target.vy -= fy; target.vz -= fz;
      });

      // 4. Update Positions & Apply Center Gravity
      nodes.forEach(n => {
        // Gentle pull towards the center (0,0,0) to keep graph visible
        n.vx -= n.x * 0.005;
        n.vy -= n.y * 0.005;
        n.vz -= n.z * 0.005;

        // Apply friction/damping to prevent infinite oscillation
        n.vx *= DAMPING; n.vy *= DAMPING; n.vz *= DAMPING;
        n.x += n.vx; n.y += n.vy; n.z += n.vz;
      });

      // 5. 3D to 2D Perspective Projection Setup
      const cosY = Math.cos(rotation.current.y);
      const sinY = Math.sin(rotation.current.y);
      const cosX = Math.cos(rotation.current.x);
      const sinX = Math.sin(rotation.current.x);
      const focalLength = 400; // Camera distance
      const cx = width / 2;
      const cy = height / 2;

      // Calculate projected coordinates for all nodes
      nodes.forEach(n => {
        // Rotate around Y axis
        let rx = n.x * cosY - n.z * sinY;
        let rz1 = n.z * cosY + n.x * sinY;
        // Rotate around X axis
        let ry = n.y * cosX - rz1 * sinX;
        let rz = rz1 * cosX + n.y * sinX;

        n.rz = rz; // Save depth for Z-sorting

        // Calculate perspective scale
        const scale = focalLength / (focalLength + rz);
        n.px = cx + rx * scale;
        n.py = cy + ry * scale;
        n.scale = scale;
      });

      // 6. Rendering
      // Draw a subtle background pattern
      ctx.fillStyle = '#fafafa';
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = '#e0e2e0';
      for(let i=0; i<width; i+=20) {
          for(let j=0; j<height; j+=20) {
              ctx.beginPath(); ctx.arc(i, j, 1, 0, Math.PI*2); ctx.fill();
          }
      }

      // Sort nodes by depth so closer nodes draw on top of farther nodes
      nodes.sort((a, b) => b.rz - a.rz);

      // Draw Links (Lines)
      linksData.forEach(link => {
        const source = nodes.find(n => n.id === link[0]);
        const target = nodes.find(n => n.id === link[1]);
        if (!source || !target) return;

        const avgDepth = (source.rz + target.rz) / 2;
        // Fade out lines that are further away in the Z-axis
        const opacity = Math.max(0.1, Math.min(0.7, 1 - (avgDepth + 200) / 400));

        ctx.beginPath();
        ctx.moveTo(source.px, source.py);
        ctx.lineTo(target.px, target.py);
        ctx.strokeStyle = `rgba(196, 199, 197, ${opacity})`;
        ctx.lineWidth = 1.5 * ((source.scale + target.scale) / 2);
        ctx.stroke();
      });

      // Draw Nodes (Circles)
      nodes.forEach(n => {
         const opacity = Math.max(0.3, Math.min(1, 1 - (n.rz + 150) / 400));
         const radius = Math.max(2, n.r * n.scale * 0.9);

         // Material Design drop shadow
         ctx.shadowColor = `rgba(0,0,0,${0.15 * opacity})`;
         ctx.shadowBlur = n.elevated ? 12 * n.scale : 4 * n.scale;
         ctx.shadowOffsetY = n.elevated ? 4 * n.scale : 2 * n.scale;

         ctx.beginPath();
         ctx.arc(n.px, n.py, radius, 0, Math.PI * 2);
         ctx.fillStyle = n.color;
         ctx.globalAlpha = opacity;
         ctx.fill();

         // Clean white stroke
         ctx.shadowColor = 'transparent';
         ctx.lineWidth = 2 * n.scale;
         ctx.strokeStyle = '#ffffff';
         ctx.stroke();

         // Typography - Only draw labels for nodes that are reasonably close
         if (n.scale > 0.65) {
             ctx.globalAlpha = opacity * (n.scale > 0.85 ? 1 : Math.max(0, (n.scale - 0.65) * 5));
             ctx.fillStyle = '#1f1f1f';
             ctx.font = `500 ${Math.max(10, 12 * n.scale)}px sans-serif`;
             ctx.textAlign = n.px > cx ? 'left' : 'right';
             ctx.textBaseline = 'middle';
             const offset = radius + (8 * n.scale);

             // Optional: Add a subtle white outline to text for legibility
             ctx.lineWidth = 2;
             ctx.strokeStyle = 'rgba(255,255,255,0.8)';
             ctx.strokeText(n.label, n.px + (n.px > cx ? offset : -offset), n.py);
             ctx.fillText(n.label, n.px + (n.px > cx ? offset : -offset), n.py);
         }
         ctx.globalAlpha = 1; // Reset alpha
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => cancelAnimationFrame(animationRef.current);
  }, []); // Empty dependency array means physics initialize once on mount

  // Interaction Handlers for Camera Rotation
  const handleMouseDown = (e) => {
    isDragging.current = true;
    previousMouse.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e) => {
    if (!isDragging.current) return;
    const deltaX = e.clientX - previousMouse.current.x;
    const deltaY = e.clientY - previousMouse.current.y;
    // Update rotation based on mouse drag distance
    rotation.current.y += deltaX * 0.008;
    rotation.current.x += deltaY * 0.008;

    // Clamp X rotation to prevent flipping upside down
    rotation.current.x = Math.max(-Math.PI/3, Math.min(Math.PI/3, rotation.current.x));
    previousMouse.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseUp = () => isDragging.current = false;

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full cursor-grab active:cursor-grabbing outline-none"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{ touchAction: 'none' }} // Prevent unwanted scrolling on touch devices
    />
  );
}
