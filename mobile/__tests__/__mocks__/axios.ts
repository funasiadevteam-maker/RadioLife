// Mock axios
const instance: any = {
  get: jest.fn(),
  post: jest.fn(),
  interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
};
instance.create = jest.fn(() => instance);
export default instance;
