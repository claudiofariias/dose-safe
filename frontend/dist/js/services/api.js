export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}
export async function api(path, options = {}) {
    const body = options.body && typeof options.body !== 'string'
        ? JSON.stringify(options.body)
        : options.body;
    const response = await fetch(path, {
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        },
        ...options,
        body,
    });
    let data = {};
    try {
        data = await response.json();
    }
    catch (_a) {
        data = {};
    }
    if (!response.ok) {
        throw new ApiError(data.error || 'Falha na operação', response.status);
    }
    return data;
}
