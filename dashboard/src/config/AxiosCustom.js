import axios from "axios";

// const baseURL = "http://localhost:6060";
const baseURL = "http://192.168.10.20:6060";

const AxiosCustom = axios.create({
    baseURL: baseURL,
    withCredentials: true
});


export default AxiosCustom;