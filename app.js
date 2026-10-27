"use strict";

(function () {
  const LEAF = window.LEAF_OS;

  if (!LEAF) {
    console.error("LEAF OS: no se encontró agents.js");
    return;
  }

  const tasks = [];
  let nextTaskId = 1;

  function createTask(agentId, description) {
    const agent = LEAF.getAgent(agentId);

    if (!agent) {
      return { success: false, message: "Agente no encontrado" };
    }

    if (typeof description !== "string" || !description.trim()) {
      return {
        success: false,
        message: "La tarea necesita una descripción"
      };
    }

    const task = {
      id: nextTaskId++,
      agentId: agent.id,
      description: description.trim(),
      status: "pending",
      createdAt: new Date().toISOString()
    };

    tasks.push(task);
    agent.tasks.push(task.id);

    return { success: true, task: { ...task } };
  }

  function getTasks() {
    return tasks.map(task => ({ ...task }));
  }

  function getTask(id) {
    const task = tasks.find(item => item.id === id);
    return task ? { ...task } : null;
  }

  function updateTaskStatus(id, status) {
    const allowed = ["pending", "working", "completed", "error"];

    if (!allowed.includes(status)) {
      return {
        success: false,
        message: "Estado de tarea no válido"
      };
    }

    const task = tasks.find(item => item.id === id);

    if (!task) {
      return { success: false, message: "Tarea no encontrada" };
    }

    task.status = status;

    const agent = LEAF.getAgent(task.agentId);

    if (agent && status === "working") {
      LEAF.setAgentStatus(agent.id, "working");
    } else if (agent && status === "error") {
      LEAF.setAgentStatus(agent.id, "error");
    } else if (agent) {
      const hasOtherActiveTask = tasks.some(
        item =>
          item.agentId === agent.id &&
          item.id !== task.id &&
          item.status === "working"
      );

      if (!hasOtherActiveTask) {
        LEAF.setAgentStatus(agent.id, "idle");
      }
    }

    return { success: true, task: { ...task } };
  }

  window.LEAF_APP = {
    version: "0.1.0",
    createTask,
    getTasks,
    getTask,
    updateTaskStatus
  };
})();
