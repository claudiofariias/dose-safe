import { Toast } from './components/Toast.js';
import { api } from './services/api.js';
import { SplashPage } from './pages/SplashPage.js';
import { LoginPage } from './pages/LoginPage.js';
import { RegisterPage } from './pages/RegisterPage.js';
import { DashboardPage } from './pages/DashboardPage.js';
import { PatientsPage } from './pages/PatientsPage.js';
import { PatientDetailPage } from './pages/PatientDetailPage.js';
import { PatientFormPage } from './pages/PatientFormPage.js';
import { PrescriptionPage } from './pages/PrescriptionPage.js';
import { AlertsPage } from './pages/AlertsPage.js';
import { HistoryPage } from './pages/HistoryPage.js';
import { CalculatorPage } from './pages/CalculatorPage.js';
import { AdherencePage } from './pages/AdherencePage.js';
import { ProfilePage } from './pages/ProfilePage.js';
export class App extends React.Component {
    constructor() {
        super(...arguments);
        this.toastTimer = null;
        this.state = {
            showSplash: true,
            booting: true,
            user: null,
            route: 'login',
            patients: [],
            medications: [],
            selectedPatient: null,
            rxItems: [],
            analysis: null,
            toastMessage: '',
            toastError: false,
        };
        this.handleHashChange = () => {
            const route = this.routeFromHash();
            if (route && route !== this.state.route) {
                this.setState({ route, ...(route === 'patientForm' ? {} : { editPatient: null }) });
            }
        };
        this.navigate = (route) => {
            if (!this.state.user && !['login', 'register'].includes(route)) {
                route = 'login';
            }
            this.setState({ route, ...(route === 'patientForm' ? {} : { editPatient: null }) }, () => this.syncHash());
        };
        this.showToast = (message, error = false) => {
            if (this.toastTimer) {
                window.clearTimeout(this.toastTimer);
            }
            this.setState({ toastMessage: message, toastError: error });
            this.toastTimer = window.setTimeout(() => {
                this.setState({ toastMessage: '', toastError: false });
            }, 2800);
        };
        this.loadDomainData = async () => {
            const [patients, medications] = await Promise.all([
                api('/api/patients'),
                api('/api/medications'),
            ]);
            this.setState({
                patients: patients.patients,
                medications: medications.medications,
                selectedPatient: this.state.selectedPatient || patients.patients[0] || null,
            });
        };
        this.handleLogin = async (user) => {
            this.setState({ user });
            try {
                await this.loadDomainData();
                this.navigate('dashboard');
            }
            catch (error) {
                this.showToast(error.message, true);
            }
        };
        this.handleLogout = async () => {
            try {
                await api('/api/auth/logout', { method: 'POST', body: {} });
            }
            catch (_a) {
                // O estado local é limpo mesmo se a sessão já tiver expirado.
            }
            this.setState({
                user: null,
                route: 'login',
                patients: [],
                medications: [],
                selectedPatient: null,
                rxItems: [],
                analysis: null,
            }, () => this.syncHash());
        };
        this.handleSelectPatient = (patient) => {
            this.setState({ selectedPatient: patient }, () => this.navigate('patientDetail'));
        };
        this.handlePatientCreated = (patient) => {
            this.setState(state => ({
                patients: [patient, ...state.patients],
                selectedPatient: patient,
            }), () => this.navigate('patientDetail'));
        };
        this.handlePatientUpdated = (patient, patients) => {
            this.setState({ patients, selectedPatient: patient, rxItems: [], analysis: null }, () => this.navigate('patientDetail'));
        };
        this.handleStartPrescription = () => {
            this.setState({ rxItems: [], analysis: null }, () => this.navigate('prescription'));
        };
    }
    componentDidMount() {
        this.bootstrap();
        window.addEventListener('hashchange', this.handleHashChange);
    }
    componentWillUnmount() {
        window.removeEventListener('hashchange', this.handleHashChange);
        if (this.toastTimer) {
            window.clearTimeout(this.toastTimer);
        }
    }
    routeFromHash() {
        const value = window.location.hash.replace(/^#/, '');
        const allowed = [
            'login',
            'register',
            'dashboard',
            'patients',
            'patientDetail',
            'patientForm',
            'prescription',
            'alerts',
            'history',
            'calculator',
            'adherence',
            'profile',
        ];
        return allowed.includes(value) ? value : null;
    }
    async bootstrap() {
        const minimumSplash = new Promise(resolve => window.setTimeout(resolve, 3000));
        try {
            const response = await api('/api/auth/me');
            if (response.user) {
                const [patients, medications] = await Promise.all([
                    api('/api/patients'),
                    api('/api/medications'),
                ]);
                const requestedRoute = this.routeFromHash();
                this.setState({
                    user: response.user,
                    patients: patients.patients,
                    medications: medications.medications,
                    selectedPatient: patients.patients[0] || null,
                    route: requestedRoute && !['login', 'register'].includes(requestedRoute)
                        ? requestedRoute
                        : 'dashboard',
                    booting: false,
                });
            }
            else {
                this.setState({ user: null, route: 'login', booting: false });
            }
        }
        catch (_a) {
            this.setState({ user: null, route: 'login', booting: false });
        }
        await minimumSplash;
        this.setState({ showSplash: false }, () => this.syncHash());
    }
    syncHash() {
        const expected = `#${this.state.route}`;
        if (window.location.hash !== expected) {
            window.history.replaceState(null, '', expected);
        }
    }
    renderRoute() {
        const user = this.state.user;
        const common = {
            route: this.state.route,
            onNavigate: this.navigate,
        };
        if (!user) {
            if (this.state.route === 'register') {
                return (React.createElement(RegisterPage, { onBack: () => this.navigate('login'), onRegistered: () => this.navigate('login'), onToast: this.showToast }));
            }
            return (React.createElement(LoginPage, { onLogin: this.handleLogin, onRegister: () => this.navigate('register'), onToast: this.showToast }));
        }
        switch (this.state.route) {
            case 'dashboard':
                return (React.createElement(DashboardPage, { ...common, user: user, onSelectPatient: this.handleSelectPatient, onToast: this.showToast }));
            case 'patients':
                return (React.createElement(PatientsPage, { ...common, patients: this.state.patients, onSelectPatient: this.handleSelectPatient }));
            case 'patientDetail':
                return (React.createElement(PatientDetailPage, { ...common, patient: this.state.selectedPatient, medications: this.state.medications, onStartPrescription: this.handleStartPrescription, onEdit: () => this.setState({ editPatient: this.state.selectedPatient }, () => this.navigate('patientForm')) }));
            case 'patientForm':
                return (React.createElement(PatientFormPage, { ...common, medications: this.state.medications, editPatient: this.state.editPatient || null, onCreated: this.handlePatientCreated, onUpdated: this.handlePatientUpdated, onToast: this.showToast }));
            case 'prescription':
                return (React.createElement(PrescriptionPage, { ...common, patients: this.state.patients, medications: this.state.medications, selectedPatient: this.state.selectedPatient, items: this.state.rxItems, analysis: this.state.analysis, onSelectPatient: patient => this.setState({ selectedPatient: patient }), onItemsChange: items => this.setState({ rxItems: items }), onAnalysis: analysis => this.setState({ analysis }), onToast: this.showToast }));
            case 'alerts':
                return React.createElement(AlertsPage, { ...common, analysis: this.state.analysis });
            case 'history':
                return (React.createElement(HistoryPage, { ...common, medications: this.state.medications, onToast: this.showToast }));
            case 'calculator':
                return React.createElement(CalculatorPage, { ...common, onToast: this.showToast });
            case 'adherence':
                return (React.createElement(AdherencePage, { ...common, patients: this.state.patients, selectedPatient: this.state.selectedPatient, onSelectPatient: patient => this.setState({ selectedPatient: patient }), onToast: this.showToast }));
            case 'profile':
                return React.createElement(ProfilePage, { ...common, user: user, onLogout: this.handleLogout, onToast: this.showToast });
            default:
                return (React.createElement(DashboardPage, { ...common, user: user, onSelectPatient: this.handleSelectPatient, onToast: this.showToast }));
        }
    }
    render() {
        if (this.state.showSplash) {
            return React.createElement(SplashPage, null);
        }
        if (this.state.booting) {
            return (React.createElement("div", { className: "phone loading" },
                React.createElement("div", null,
                    React.createElement("div", { className: "spinner" }),
                    React.createElement("p", null, "Carregando..."))));
        }
        return (React.createElement("div", { className: "app-host" },
            this.renderRoute(),
            React.createElement(Toast, { message: this.state.toastMessage, error: this.state.toastError })));
    }
}
