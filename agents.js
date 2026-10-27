"use strict";

const LEAF_OS = {
  name: "LEAF",
  version: "0.1.0",
  role: "Asistente principal",
  status: "ready",

  agents: [
    {
      id: "clip-agent",
      name: "Clip Agent",
      role: "Preparar clips de video",
      status: "idle",
      tasks: []
    },
    {
      id: "trend-agent",
      name: "Trend Agent",
      role: "Analizar tendencias",
      status: "idle",
      tasks: []
    },
    {
      id: "monitor-agent",
      name: "Monitor Agent",
      role: "Supervisar redes sociales",
      status: "idle",
      tasks: []
    },
    {
      id: "quality-agent",
      name: "Quality Agent",
      role: "Revisar la calidad del contenido",
      status: "idle",
      tasks: []
    }
  ],

  getAgents() {
    return this.agents;
  },

  getAgent(id) {
    return this.agents.find(agent => agent.id === id) || null;
  },

  getStatus() {
    return {
      name: this.name,
      version: this.version,
      status: this.status,
      totalAgents: this.agents.length,
      activeAgents: this.agents.filter(
        agent => agent.status === "working"
      ).length
    };
  },

  setAgentStatus(id, status) {
    const allowedStatuses = ["idle", "working", "error"];
    const agent = this.getAgent(id);

    if (!agent) {
      return {
        success: false,
        message: "Agente no encontrado"
      };
    }

    if (!allowedStatuses.includes(status)) {
      return {
        success: false,
        message: "Estado no válido"
      };
    }

    agent.status = status;

    return {
      success: true,
      agent: agent.name,
      status: agent.status
    };
  }
};

window.LEAF_OS = LEAF_OS;
