import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DeclarationComponent } from './declaration/declaration.component';
import { PreprocessingComponent } from './preprocessing/preprocessing.component';
import { ModelingComponent } from './modeling/modeling.component';
import { EvaluationComponent } from './evaluation/evaluation.component';
import { DeploymentComponent } from './deployment/deployment.component';
import { ModelDevelopmentComponent } from './model-development/model-development.component';
import { HomeComponent } from './home/home.component';

const routes: Routes = [
  { path: 'home', component: HomeComponent },
  { path: '', redirectTo: '/model-development', pathMatch: 'full' },
  {
    path: 'model-development',
    component: ModelDevelopmentComponent,
    children: [
      { path: 'declaration', component: DeclarationComponent },
      { path: 'preprocessing', component: PreprocessingComponent },
      { path: 'modeling', component: ModelingComponent },
      { path: 'evaluation', component: EvaluationComponent },
      { path: 'deployment', component: DeploymentComponent },
      { path: '', redirectTo: 'declaration', pathMatch: 'full' }
    ]
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }