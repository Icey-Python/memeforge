// Desc: Configuration file for the client side
// e.g. serverUrl, apiBase, imageBase, socketUrl

import axios from 'axios';

export const serverUrl = process.env.NEXT_PUBLIC_SERVER_URL;

export const apiBase = axios.create({
	baseURL: `${serverUrl}/api/v1`,
	withCredentials: true
});

//export const imageBase = process.env.NEXT_PUBLIC_IMAGE_URL as string

//export const socketUrl = process.env.NEXT_PUBLIC_SOCKET_URL as string
