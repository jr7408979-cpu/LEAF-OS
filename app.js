
"use strict";

(function () {
  const API_URL = "https://leaf-os.onrender.com";

  let tasks = [];
  let agents = [];
  let nextTaskId = 1;

  async function request(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Error al comunicarse con LEAF OS");
    }

    return data;
  }

  function normalizeTask(task) {
    return {
      ...task,
      agentId: task.agent_id || task.agentId,
      createdAt: task.created_at || task.createdAt
    };
  }

  async function refreshData() {
    const [serverTasks, serverAgents] = await Promise.all([
      request("/api/tasks"),
      request("/api/agents")
    ]);

    tasks = serverTasks.map(normalizeTask);
    agents = serverAgents;

    return {
      tasks: getTasks(),
      agents: getAgents()
    };
  }

  async function createTask(agentId, description, priority = "Normal") {
    if (typeof description !== "string" || !description.trim()) {
      return {
        success: false,
        message: "La tarea necesita una descripción"
      };
    }

    try {
      const task = await request("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          agent_id: agentId,
          description: description.trim(),
          priority
        })
      });

      const normalized = normalizeTask(task);
      tasks.push(normalized);

      return {
        success: true,
        task: { ...normalized }
      };
    } catch (error) {
      return {
        success: false,
        message: error.message
      };
    }
  }

  function getTasks() {
    return tasks.map(task => ({ ...task }));
  }

  function getTask(id) {
    const task = tasks.find(item => String(item.id) === String(id));
    return task ? { ...task } : null;
  }

  async function updateTaskStatus(id, status) {
    const allowed = ["pending", "working", "completed", "error"];

    if (!allowed.includes(status)) {
      return {
        success: false,
        message: "Estado de tarea no válido"
      };
    }

    try {
      const updated = await request(
        `/api/tasks/${encodeURIComponent(id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status })
        }
      );

      const normalized = normalizeTask(updated);
      const index = tasks.findIndex(
        item => String(item.id) === String(id)
      );

      if (index >= 0) {
        tasks[index] = normalized;
      } else {
        tasks.push(normalized);
      }

      return {
        success: true,
        task: { ...normalized }
      };
    } catch (error) {
      return {
        success: false,
        message: error.message
      };
    }
  }

  function getAgents() {
    return agents.map(agent => ({ ...agent }));
  }

  function getAgent(id) {
    const agent = agents.find(item => item.id === id);
    return agent ? { ...agent } : null;
  }

  async function getActivity(limit = 30) {
    return request(`/api/activity?limit=${encodeURIComponent(limit)}`);
  }

  async function getSystemStatus() {
    return request("/api/status");
  }

  window.LEAF_APP = {
    version: "0.2.0",
    refreshData,
    createTask,
    getTasks,
    getTask,
    updateTaskStatus,
    getAgents,
    getAgent,
    getActivity,
    getSystemStatus
  };

  refreshData().catch(error => {
    console.error("LEAF OS: no se pudo conectar con el backend:", error);
  });
})();
