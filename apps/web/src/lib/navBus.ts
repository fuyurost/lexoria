import { inject, reactive, type InjectionKey } from 'vue';

/** App-level navigation bus: lets any view request search focus (the '/' shortcut). */
export interface NavBusState {
  searchTick: number;
}

export const navBusKey: InjectionKey<NavBusState> = Symbol('nav-bus');

export function createNavBus(): NavBusState {
  return reactive({ searchTick: 0 });
}

export function useNavBus(): NavBusState | null {
  return inject(navBusKey, null);
}
